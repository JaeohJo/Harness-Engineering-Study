"""Antigravity 하네스 시스템의 핵심 데이터 모델 및 도메인 객체 모듈.

Pydantic v2를 기반으로 타입 안정성을 보장하며, CLI 스트리밍 이벤트,
태스크 사양, 실행 결과, 평가 결과, 텔레메트리 데이터 등을 정의합니다.
"""

from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StreamEventType(str, Enum):
    """agy CLI 스트리밍 출력(stream-json)에서 전달되는 이벤트 유형."""
    THOUGHT = "thought"          # 모델의 추론(생각) 과정
    TOOL_CALL = "tool_call"      # 도구 호출 요청
    TOOL_RESULT = "tool_result"  # 도구 실행 결과 반환
    DELTA = "delta"              # 사용자 대상 텍스트 응답 조각
    DONE = "done"                # 세션 또는 턴 완료 신호
    ERROR = "error"              # 에이전트 실행 중 오류 발생
    SYSTEM = "system"            # 시스템 레벨 안내 메시지
    UNKNOWN = "unknown"          # 알 수 없는 기타 이벤트


class StreamEvent(BaseModel):
    """agy CLI의 NDJSON 라인 하나를 구조화한 스트림 이벤트 객체."""
    type: StreamEventType
    timestamp: float = Field(default_factory=time.time, description="이벤트 수신 유닉스 타임스탬프")
    raw_payload: Dict[str, Any] = Field(default_factory=dict, description="원본 JSON 페이로드")
    content: Optional[str] = Field(default=None, description="텍스트 메시지 내용 또는 델타 조각")
    tool_name: Optional[str] = Field(default=None, description="호출된 도구 이름 (예: run_command)")
    tool_args: Optional[Dict[str, Any]] = Field(default=None, description="도구 호출 인자 딕셔너리")
    tool_call_id: Optional[str] = Field(default=None, description="도구 호출 식별자 ID")

    @classmethod
    def from_ndjson(cls, line: str) -> Optional[StreamEvent]:
        """단일 NDJSON 라인을 파싱하여 StreamEvent 객체로 변환합니다.

        빈 라인은 무시(None 반환)하며, JSON 규격이 아닌 경우 UNKNOWN 타입으로 안전하게 래핑합니다.
        """
        clean_line = line.strip()
        if not clean_line:
            return None

        # 1. JSON 역직렬화 시도
        try:
            data = json.loads(clean_line)
        except json.JSONDecodeError:
            # 플레인 텍스트가 섞여 들어오는 경우 처리
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

        # 2. agy CLI 및 LLM 스트림 표준 시그니처 분석
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

        # 3. 주요 필드 추출 (다양한 CLI 출력 포맷에 대응하는 폴백 구조)
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
    """단일 태스크에 대한 에이전트 실행 결과 요약 객체."""
    task_id: str
    conversation_id: Optional[str] = Field(default=None, description="Antigravity 세션 대화 ID")
    exit_code: int = Field(default=0, description="프로세스 종료 코드 (0: 정상)")
    events: List[StreamEvent] = Field(default_factory=list, description="수신된 전체 스트림 이벤트 목록")
    stdout: str = Field(default="", description="표준 출력 전체 원본 문자열")
    stderr: str = Field(default="", description="표준 에러 전체 원본 문자열")
    duration_seconds: float = Field(default=0.0, description="실행 소요 시간(초)")
    timed_out: bool = Field(default=False, description="타임아웃 발생 여부")
    error_message: Optional[str] = Field(default=None, description="실패 원인 메시지")
    final_response: str = Field(default="", description="에이전트의 최종 텍스트 응답")

    @property
    def is_success(self) -> bool:
        """프로세스 크래시나 타임아웃 없이 정상 완료되었는지 여부."""
        return self.exit_code == 0 and not self.timed_out and self.error_message is None


class TaskSpec(BaseModel):
    """에이전트가 해결해야 할 엔지니어링 문제 및 환경 사양 정의."""
    task_id: str = Field(description="태스크 고유 식별자")
    description: str = Field(description="에이전트에게 전달될 프롬프트/문제 설명")
    repo_path: Optional[str] = Field(default=None, description="대상 소스코드 저장소 경로")
    base_commit: Optional[str] = Field(default=None, description="체크아웃할 베이스 Git 커밋 또는 브랜치")
    branch: Optional[str] = Field(default=None, description="체크아웃할 Git 브랜치명 (base_commit의 직관적 별칭)")
    test_patch: Optional[str] = Field(default=None, description="문제 재현 및 검증을 위한 테스트 패치")
    golden_patch: Optional[str] = Field(default=None, description="정답 레퍼런스 패치 (선택 사항)")
    test_command: Optional[str] = Field(default=None, description="해결 여부를 검증할 테스트 실행 명령어")
    timeout_seconds: Optional[float] = Field(default=None, description="태스크별 개별 타임아웃 제한(초)")
    initial_files: Dict[str, str] = Field(
        default_factory=dict,
        description="태스크 시작 전 워크스페이스에 사전 생성할 초기 파일 맵 (상대경로 -> 내용)",
    )
    setup_command: Optional[str] = Field(
        default=None,
        description="에이전트 실행 전 워크스페이스에서 실행할 사전 설정 명령어",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="도메인별 추가 메타데이터")


class EvalStatus(str, Enum):
    """태스크 평가 최종 판정 상태."""
    PASS = "PASS"        # 테스트 통과 및 해결 성공
    FAIL = "FAIL"        # 테스트 실패 또는 검증 불합격
    ERROR = "ERROR"      # 문법 에러, 런타임 크래시 등 비정상 오류
    TIMEOUT = "TIMEOUT"  # 테스트 실행 시간 초과
    SKIPPED = "SKIPPED"  # 평가 건너뜀


class EvalResult(BaseModel):
    """에이전트가 생성한 코드 수정본에 대한 최종 평가 결과 객체."""
    task_id: str
    status: EvalStatus = Field(description="최종 성공/실패 상태")
    tests_passed: List[str] = Field(default_factory=list, description="통과한 단위 테스트 목록")
    tests_failed: List[str] = Field(default_factory=list, description="실패한 단위 테스트 목록")
    tests_errored: List[str] = Field(default_factory=list, description="에러가 발생한 테스트 목록")
    diff: str = Field(default="", description="에이전트가 수정한 최종 Git Diff")
    message: str = Field(default="", description="평가 요약 메시지")
    duration_seconds: float = Field(default=0.0, description="평가 실행 시간(초)")
    details: Dict[str, Any] = Field(default_factory=dict, description="상세 출력 및 부가 정보")


class TelemetryData(BaseModel):
    """에이전트 세션의 추론 과정 및 도구 호출 관측성 메트릭 데이터."""
    task_id: str
    conversation_id: Optional[str] = Field(default=None, description="대화 세션 ID")
    duration_seconds: float = Field(default=0.0, description="전체 턴 진행 시간(초)")
    total_turns: int = Field(default=0, description="진행된 대화/스텝 총 턴 수")
    thinking_token_count: int = Field(default=0, description="추론(Thinking) 단계 추정 토큰 수")
    total_tool_calls: int = Field(default=0, description="수행된 전체 도구 호출 횟수")
    tool_call_counts: Dict[str, int] = Field(default_factory=dict, description="도구별 호출 빈도 통계")
    tool_error_counts: Dict[str, int] = Field(default_factory=dict, description="도구별 에러 발생 횟수")
    files_modified: List[str] = Field(default_factory=list, description="수정/생성된 파일 상대 경로 목록")
    lines_added: int = Field(default=0, description="추가된 코드 라인 수")
    lines_removed: int = Field(default=0, description="삭제된 코드 라인 수")
