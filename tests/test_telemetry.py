"""Unit tests for TranscriptParser and BenchmarkReport."""

import json
from pathlib import Path
import pytest

from harness.core.models import EvalResult, EvalStatus, TelemetryData
from harness.telemetry.transcript import TranscriptParser
from harness.telemetry.reporter import BenchmarkReport


def test_transcript_parser(tmp_path: Path):
    transcript_file = tmp_path / "transcript.jsonl"
    lines = [
        {
            "step_index": 0,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "content": "Fix the bug in add function",
        },
        {
            "step_index": 1,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "thinking": "Let me first check the code implementation in calc.py to see where the addition fails.",
            "tool_calls": [
                {"name": "view_file", "args": {"AbsolutePath": "/src/calc.py"}},
            ],
            "status": "DONE",
        },
        {
            "step_index": 2,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "thinking": "Now replace the minus with plus.",
            "tool_calls": [
                {"name": "replace_file_content", "args": {"TargetFile": "/src/calc.py"}},
                {"name": "run_command", "args": {"CommandLine": "pytest"}},
            ],
            "status": "DONE",
        },
    ]

    with open(transcript_file, "w", encoding="utf-8") as f:
        for item in lines:
            f.write(json.dumps(item) + "\n")

    parser = TranscriptParser()
    steps = parser.parse_file(transcript_file)
    assert len(steps) == 3
    assert steps[1].tool_calls[0]["name"] == "view_file"

    telemetry = parser.extract_telemetry(
        task_id="calc_task",
        transcript_path=transcript_file,
        duration_seconds=12.5,
    )

    assert telemetry.task_id == "calc_task"
    assert telemetry.total_turns == 3
    assert telemetry.total_tool_calls == 3
    assert telemetry.tool_call_counts["view_file"] == 1
    assert telemetry.tool_call_counts["replace_file_content"] == 1
    assert telemetry.tool_call_counts["run_command"] == 1
    assert telemetry.thinking_token_count > 0


def test_benchmark_report_generation(tmp_path: Path):
    evals = [
        EvalResult(task_id="t1", status=EvalStatus.PASS, duration_seconds=5.0, tests_passed=["test_1"]),
        EvalResult(task_id="t2", status=EvalStatus.FAIL, duration_seconds=8.0, tests_failed=["test_2"], message="Assertion failed"),
    ]
    telems = [
        TelemetryData(task_id="t1", total_turns=2, total_tool_calls=2, tool_call_counts={"run_command": 2}),
        TelemetryData(task_id="t2", total_turns=4, total_tool_calls=3, tool_call_counts={"edit_file": 3}),
    ]

    report = BenchmarkReport(eval_results=evals, telemetry_data=telems, model_name="gemini-1.5-pro")

    assert report.total_tasks == 2
    assert report.passed_tasks == 1
    assert report.failed_tasks == 1
    assert report.pass_rate == 50.0

    json_file, md_file = report.save(tmp_path)
    assert json_file.exists()
    assert md_file.exists()

    md_content = md_file.read_text(encoding="utf-8")
    assert "Antigravity CLI Benchmark Report" in md_content
    assert "50.0%" in md_content
    assert "gemini-1.5-pro" in md_content
