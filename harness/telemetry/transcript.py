"""Antigravity Brain 세션 트랜스크립트(JSONL) 파서 모듈.

Antigravity CLI 실행 중 ~/.gemini/antigravity-cli/brain/<id>/.system_generated/logs/ 하위에
생성되는 transcript.jsonl 파일을 파싱하여, 모델의 추론(Thinking) 토큰, 턴 수, 도구 호출 빈도 등을 집계합니다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.core.logging import logger
from harness.core.models import TelemetryData


class TranscriptStep:
    """Antigravity 대화 트랜스크립트의 단일 단계(Step) 객체."""

    def __init__(self, data: Dict[str, Any]):
        self.raw = data
        self.step_index: int = data.get("step_index", 0)
        self.source: str = data.get("source", "")
        self.step_type: str = data.get("type", "")
        self.created_at: str = data.get("created_at", "")
        self.content: str = data.get("content", "") or ""
        self.thinking: str = data.get("thinking", "") or ""
        self.tool_calls: List[Dict[str, Any]] = data.get("tool_calls") or []
        self.status: str = data.get("status", "")


class TranscriptParser:
    """에이전트 세션의 transcript.jsonl 파일을 탐색하고 메트릭을 추출하는 파서."""

    def __init__(self, app_data_dir: Optional[str | Path] = None):
        if app_data_dir:
            self.app_data_dir = Path(app_data_dir)
        else:
            home = Path.home()
            self.app_data_dir = home / ".gemini" / "antigravity-cli"

    def find_transcript_path(self, conversation_id: str) -> Optional[Path]:
        """대화 ID를 기반으로 로컬 파일시스템의 transcript.jsonl 파일 경로를 조회합니다."""
        candidate = (
            self.app_data_dir
            / "brain"
            / conversation_id
            / ".system_generated"
            / "logs"
            / "transcript.jsonl"
        )
        if candidate.exists():
            return candidate
        return None

    def parse_file(self, file_path: str | Path) -> List[TranscriptStep]:
        """JSONL 트랜스크립트 파일을 파싱하여 단계별 TranscriptStep 리스트로 반환합니다."""
        path = Path(file_path).resolve()
        if not path.exists():
            logger.warning(f"트랜스크립트 파일을 찾을 수 없습니다: {path}")
            return []

        steps: List[TranscriptStep] = []
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    data = json.loads(line_str)
                    if isinstance(data, dict):
                        steps.append(TranscriptStep(data))
                except json.JSONDecodeError:
                    continue

        return steps

    def extract_telemetry(
        self,
        task_id: str,
        conversation_id: Optional[str] = None,
        transcript_path: Optional[str | Path] = None,
        duration_seconds: float = 0.0,
    ) -> TelemetryData:
        """트랜스크립트 파일로부터 모델의 추론량 및 도구 사용 통계를 집계하여 반환합니다."""
        target_path = Path(transcript_path) if transcript_path else None
        if not target_path and conversation_id:
            target_path = self.find_transcript_path(conversation_id)

        steps = self.parse_file(target_path) if target_path else []

        total_turns = len(steps)
        thinking_chars = 0
        tool_counts: Dict[str, int] = {}
        tool_errors: Dict[str, int] = {}

        # 단계별 추론 텍스트 및 도구 호출 빈도 집계
        for step in steps:
            if step.thinking:
                thinking_chars += len(step.thinking)

            for call in step.tool_calls:
                call_name = call.get("tool_name") or call.get("name") or "unknown_tool"
                tool_counts[call_name] = tool_counts.get(call_name, 0) + 1

            if step.status and step.status.lower() in ("error", "failed"):
                step_name = step.step_type or "step_error"
                tool_errors[step_name] = tool_errors.get(step_name, 0) + 1

        total_tool_calls = sum(tool_counts.values())
        # 영어/코드 기준 대략 4글자당 1토큰으로 추론 토큰량 추정
        estimated_thinking_tokens = thinking_chars // 4

        return TelemetryData(
            task_id=task_id,
            conversation_id=conversation_id,
            duration_seconds=duration_seconds,
            total_turns=total_turns,
            thinking_token_count=estimated_thinking_tokens,
            total_tool_calls=total_tool_calls,
            tool_call_counts=tool_counts,
            tool_error_counts=tool_errors,
        )
