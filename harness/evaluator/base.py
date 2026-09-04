"""평가 및 검증 엔진 기본 인터페이스 정의 모듈."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from harness.core.models import EvalResult, TaskSpec


class BaseEvaluator(ABC):
    """태스크별 코드 수정 결과물의 정답 여부를 채점하고 검증하는 추상 인터페이스."""

    @abstractmethod
    def evaluate(
        self,
        workspace_dir: str | Path,
        task: TaskSpec,
        diff: Optional[str] = None,
        **kwargs,
    ) -> EvalResult:
        """에이전트의 작업 결과가 태스크 사양을 만족하는지 검증하고 EvalResult를 반환합니다."""
        pass
