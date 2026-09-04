"""Core data models and domain objects for the Antigravity Harness system."""

from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StreamEventType(str, Enum):
    """Enumeration of event types produced by agy CLI streaming."""
    THOUGHT = "thought"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    DELTA = "delta"
    DONE = "done"
    ERROR = "error"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class StreamEvent(BaseModel):
    """Represents a single parsed event from the agy CLI stream-json output."""
    type: StreamEventType
    timestamp: float = Field(default_factory=time.time)
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_call_id: Optional[str] = None

    @classmethod
    def from_ndjson(cls, line: str) -> Optional[StreamEvent]:
        """Parse a single NDJSON line into a structured StreamEvent."""
        clean_line = line.strip()
        if not clean_line:
            return None

        try:
            data = json.loads(clean_line)
        except json.JSONDecodeError:
            return cls(
                type=StreamEventType.UNKNOWN,
                raw_payload={"raw_line": clean_line},
                content=clean_line,
            )

        if not isinstance(data, dict):
            return cls(
                type=StreamEventType.UNKNOWN,
                raw_payload={"data": data},
                content=str(data),
            )

        # Detect event type based on standard agy/stream-json signatures
        event_type = StreamEventType.UNKNOWN
        raw_type = data.get("type", "").lower()

        if "thought" in raw_type or "thinking" in data:
            event_type = StreamEventType.THOUGHT
        elif "tool_call" in raw_type or "toolCall" in data or "function_call" in data:
            event_type = StreamEventType.TOOL_CALL
        elif "tool_result" in raw_type or "toolResult" in data:
            event_type = StreamEventType.TOOL_RESULT
        elif "delta" in raw_type or "content_delta" in raw_type:
            event_type = StreamEventType.DELTA
        elif "done" in raw_type or data.get("done") is True:
            event_type = StreamEventType.DONE
        elif "error" in raw_type or "error" in data:
            event_type = StreamEventType.ERROR
        elif "system" in raw_type:
            event_type = StreamEventType.SYSTEM

        content = data.get("content") or data.get("text") or data.get("delta") or data.get("message")
        tool_name = data.get("tool_name") or data.get("name")
        tool_args = data.get("tool_args") or data.get("arguments") or data.get("args")
        tool_call_id = data.get("tool_call_id") or data.get("call_id") or data.get("id")

        return cls(
            type=event_type,
            raw_payload=data,
            content=content if isinstance(content, str) else None,
            tool_name=tool_name if isinstance(tool_name, str) else None,
            tool_args=tool_args if isinstance(tool_args, dict) else None,
            tool_call_id=str(tool_call_id) if tool_call_id is not None else None,
        )


class ExecutionResult(BaseModel):
    """Complete summary of an agent run for a single task."""
    task_id: str
    conversation_id: Optional[str] = None
    exit_code: int = 0
    events: List[StreamEvent] = Field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    duration_seconds: float = 0.0
    timed_out: bool = False
    error_message: Optional[str] = None
    final_response: str = ""

    @property
    def is_success(self) -> bool:
        """Whether the agent execution completed without crash or timeout."""
        return self.exit_code == 0 and not self.timed_out and self.error_message is None


class TaskSpec(BaseModel):
    """Specification of an engineering task to be tackled by the agent."""
    task_id: str
    description: str
    repo_path: Optional[str] = None
    base_commit: Optional[str] = None
    test_patch: Optional[str] = None
    golden_patch: Optional[str] = None
    test_command: Optional[str] = None
    timeout_seconds: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvalStatus(str, Enum):
    """Outcome status of task evaluation."""
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    SKIPPED = "SKIPPED"


class EvalResult(BaseModel):
    """Result of evaluating the agent's work on a task."""
    task_id: str
    status: EvalStatus
    tests_passed: List[str] = Field(default_factory=list)
    tests_failed: List[str] = Field(default_factory=list)
    tests_errored: List[str] = Field(default_factory=list)
    diff: str = ""
    message: str = ""
    duration_seconds: float = 0.0
    details: Dict[str, Any] = Field(default_factory=dict)


class TelemetryData(BaseModel):
    """Detailed telemetry and observability metrics collected from an agent run."""
    task_id: str
    conversation_id: Optional[str] = None
    duration_seconds: float = 0.0
    total_turns: int = 0
    thinking_token_count: int = 0
    total_tool_calls: int = 0
    tool_call_counts: Dict[str, int] = Field(default_factory=dict)
    tool_error_counts: Dict[str, int] = Field(default_factory=dict)
    files_modified: List[str] = Field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0
