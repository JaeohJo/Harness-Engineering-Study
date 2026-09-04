"""에이전트 실행기(Runner) 기본 인터페이스 정의 모듈."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional
from harness.core.models import ExecutionResult, StreamEvent


class BaseRunner(ABC):
    """AI 코딩 에이전트 실행을 위한 추상 기본 인터페이스.

    모든 구체적 실행기(CLI 서브프로세스, Python SDK 기반 등)는 본 인터페이스를 상속받아 구현합니다.
    """

    @abstractmethod
    async def run(
        self,
        prompt: str,
        workspace_dir: str,
        task_id: str = "default_task",
        on_event: Optional[Callable[[StreamEvent], None]] = None,
        **kwargs,
    ) -> ExecutionResult:
        """격리된 워크스페이스 디렉터리에서 비동기로 에이전트 작업을 실행합니다."""
        pass

    @abstractmethod
    def run_sync(
        self,
        prompt: str,
        workspace_dir: str,
        task_id: str = "default_task",
        on_event: Optional[Callable[[StreamEvent], None]] = None,
        **kwargs,
    ) -> ExecutionResult:
        """에이전트 작업을 동기 방식으로 블로킹 호출하여 실행합니다."""
        pass
