"""Base interface for task evaluation and verification engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from harness.core.models import EvalResult, TaskSpec


class BaseEvaluator(ABC):
    """Abstract interface for verifying agent changes on a task."""

    @abstractmethod
    def evaluate(
        self,
        workspace_dir: str | Path,
        task: TaskSpec,
        diff: Optional[str] = None,
        **kwargs,
    ) -> EvalResult:
        """Evaluates whether the agent's work in the workspace satisfies the task specification."""
        pass
