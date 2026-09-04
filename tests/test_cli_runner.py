"""Unit tests for CliRunner and StreamEvent streaming parser."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from harness.core.models import StreamEvent, StreamEventType
from harness.core.config import RunnerConfig
from harness.runner.cli_runner import CliRunner


def test_stream_event_parsing():
    # Test Thought event
    thought_line = '{"type": "thought", "content": "I need to inspect the code."}'
    event = StreamEvent.from_ndjson(thought_line)
    assert event is not None
    assert event.type == StreamEventType.THOUGHT
    assert event.content == "I need to inspect the code."

    # Test Tool Call event
    tool_line = '{"type": "tool_call", "name": "run_command", "args": {"CommandLine": "ls -la"}, "id": "call_123"}'
    event = StreamEvent.from_ndjson(tool_line)
    assert event is not None
    assert event.type == StreamEventType.TOOL_CALL
    assert event.tool_name == "run_command"
    assert event.tool_args == {"CommandLine": "ls -la"}
    assert event.tool_call_id == "call_123"

    # Test Delta event
    delta_line = '{"type": "delta", "delta": "Here is the fix."}'
    event = StreamEvent.from_ndjson(delta_line)
    assert event is not None
    assert event.type == StreamEventType.DELTA
    assert event.content == "Here is the fix."

    # Test Empty line
    assert StreamEvent.from_ndjson("   \n") is None

    # Test Malformed JSON line
    malformed = "Plain text output not in JSON format"
    event = StreamEvent.from_ndjson(malformed)
    assert event is not None
    assert event.type == StreamEventType.UNKNOWN
    assert event.content == malformed


@pytest.mark.asyncio
async def test_cli_runner_success(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    runner = CliRunner(RunnerConfig(agy_bin_path="agy"))

    # Create mock subprocess
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_process.pid = 12345

    stdout_data = [
        b'{"type": "thought", "content": "Analyzing repository..."}\n',
        b'{"type": "tool_call", "name": "view_file", "args": {"AbsolutePath": "/app/main.py"}}\n',
        b'{"type": "delta", "delta": "Fixed the issue."}\n',
        b'{"type": "done", "conversation_id": "conv_999"}\n',
        b"",
    ]
    stdout_stream = asyncio.StreamReader()
    for chunk in stdout_data:
        stdout_stream.feed_data(chunk)
    stdout_stream.feed_eof()

    stderr_stream = asyncio.StreamReader()
    stderr_stream.feed_eof()

    mock_process.stdout = stdout_stream
    mock_process.stderr = stderr_stream
    mock_process.wait = AsyncMock(return_value=0)

    events_received = []

    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        result = await runner.run(
            prompt="Fix bug #10",
            workspace_dir=str(workspace),
            task_id="task_10",
            on_event=lambda e: events_received.append(e),
        )

    assert result.is_success
    assert result.task_id == "task_10"
    assert result.conversation_id == "conv_999"
    assert result.exit_code == 0
    assert len(events_received) == 4
    assert "Fixed the issue." in result.final_response


@pytest.mark.asyncio
async def test_cli_runner_timeout(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    runner = CliRunner(RunnerConfig(timeout_seconds=0.1))

    mock_process = MagicMock()
    mock_process.returncode = None
    mock_process.pid = 54321

    # Simulate hung stream
    stdout_stream = asyncio.StreamReader()
    stderr_stream = asyncio.StreamReader()
    mock_process.stdout = stdout_stream
    mock_process.stderr = stderr_stream

    async def hang():
        await asyncio.sleep(10)
        return 0

    mock_process.wait = hang

    with patch("asyncio.create_subprocess_exec", return_value=mock_process), \
         patch("harness.runner.cli_runner.os.killpg", return_value=None):
        result = await runner.run(
            prompt="Long task",
            workspace_dir=str(workspace),
            task_id="timeout_task",
        )

    assert result.timed_out is True
    assert result.exit_code == -1
    assert "timed out" in (result.error_message or "").lower()
