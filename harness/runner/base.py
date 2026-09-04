"""Base interface for agent runners."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional
from harness.core.models import ExecutionResult, StreamEvent


class BaseRunner(ABC):
    """Abstract interface defining the execution contract for an AI agent."""

    @abstractmethod
    async def run(
        self,
        prompt: str,
        workspace_dir: str,
        task_id: str = "default_task",
        on_event: Optional[Callable[[StreamEvent], None]] = None,
        **kwargs,
    ) -> ExecutionResult:
        """Executes a prompt against the given workspace asynchronously."""
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
        """Executes a prompt against the given workspace synchronously."""
        pass
