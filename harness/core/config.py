"""Antigravity 하네스 시스템의 설정 관리 및 로더 모듈.

YAML 파일 기반의 하네스 설정(HarnessConfig) 및 agy CLI 구동 옵션(RunnerConfig)을 정의합니다.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Literal, Optional
import yaml
from pydantic import BaseModel, Field


class RunnerConfig(BaseModel):
    """Antigravity CLI (agy) 실행을 위한 파라미터 설정."""
    model: Optional[str] = Field(default=None, description="세션에 사용할 LLM 모델 식별자")
    effort: Optional[Literal["low", "medium", "high"]] = Field(
        default=None, description="모델의 추론(Reasoning) 노력 수준"
    )
    mode: Optional[Literal["accept-edits", "plan"]] = Field(
        default="accept-edits", description="에이전트 실행 모드 (accept-edits: 코드 자동 수정, plan: 계획 수립)"
    )
    dangerously_skip_permissions: bool = Field(
        default=True,
        description="도구 실행 시 사용자 승인 프롬프트 건너뛰기 (비대화형 자동화의 핵심 옵션)",
    )
    sandbox: bool = Field(
        default=False,
        description="터미널 명령어 제한이 걸린 샌드박스 모드 활성화",
    )
    timeout_seconds: float = Field(
        default=300.0, description="print 모드 최대 실행 대기 시간(초)"
    )
    agy_bin_path: str = Field(
        default="agy", description="Antigravity CLI 실행 바이너리 파일 경로"
    )
    extra_flags: List[str] = Field(
        default_factory=list, description="사용자 정의 추가 CLI 플래그 목록"
    )

    def build_cli_args(
        self,
        prompt: Optional[str] = None,
        workspace_dir: Optional[str] = None,
        log_file: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> List[str]:
        """비대화형(Headless) agy CLI 호출을 위한 커맨드라인 인자 리스트를 생성합니다."""
        args = [self.agy_bin_path]

        # 1. 비대화형 스트리밍 출력 모드 강제 지정
        args.append("--print")
        args.extend(["--output-format", "stream-json"])

        # 2. 자동화 파이프라인 필수 권한 플래그
        if self.dangerously_skip_permissions:
            args.append("--dangerously-skip-permissions")

        if self.sandbox:
            args.append("--sandbox")

        # 3. 모델 및 추론 파라미터 전달
        if self.model:
            args.extend(["--model", self.model])

        if self.effort:
            args.extend(["--effort", self.effort])

        if self.mode:
            args.extend(["--mode", self.mode])

        # 4. 타임아웃 포맷팅 (태스크별 오버라이드 우선 적용, 예: 5m0s)
        effective_timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        if effective_timeout:
            timeout_m = int(effective_timeout // 60)
            timeout_s = int(effective_timeout % 60)
            args.extend(["--print-timeout", f"{timeout_m}m{timeout_s}s"])

        if log_file:
            args.extend(["--log-file", str(log_file)])

        # 5. 작업 대상 격리 워크스페이스 디렉터리 바인딩
        if workspace_dir:
            args.extend(["--add-dir", str(workspace_dir)])

        # 6. 추가 사용자 정의 플래그 추가
        args.extend(self.extra_flags)

        # 7. 마지막 인자로 프롬프트 전달
        if prompt:
            args.append(prompt)

        return args


class HarnessConfig(BaseModel):
    """벤치마크 평가 실행 및 작업 환경을 조율하는 전역 하네스 설정."""
    output_dir: Path = Field(
        default_factory=lambda: Path("reports"),
        description="평가 결과 리포트, diff 및 텔레메트리가 저장될 기본 디렉터리",
    )
    runner: RunnerConfig = Field(
        default_factory=RunnerConfig, description="CLI 실행기 세부 설정"
    )
    cleanup_worktree: bool = Field(
        default=True, description="태스크 실행 완료 후 격리된 Git Worktree 자동 삭제 여부"
    )
    enable_guardrails: bool = Field(
        default=True, description="워크스페이스에 보안 및 품질 검사용 .agents/hooks.json 주입 여부"
    )
    concurrency: int = Field(
        default=1, description="동시 실행 가능한 최대 태스크 수"
    )

    @classmethod
    def from_yaml(cls, path: str | Path) -> HarnessConfig:
        """YAML 파일로부터 설정을 로드합니다."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return cls.model_validate(data)

    def to_yaml(self, path: str | Path) -> None:
        """현재 설정을 YAML 파일로 직렬화하여 저장합니다."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(self.model_dump(mode="json"), f, default_flow_style=False, sort_keys=False)
