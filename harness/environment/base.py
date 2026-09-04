"""Base interface for workspace execution environments."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional


class BaseEnvironment(ABC):
    """Abstract interface defining the lifecycle of a task workspace environment."""

    @abstractmethod
    def setup(self) -> Path:
        """Initializes and isolates the workspace, returning the working directory path."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Tears down the isolated workspace and cleans up resources."""
        pass

    @abstractmethod
    def get_diff(self) -> str:
        """Returns the unified git/file diff representing all modifications made in this workspace."""
        pass

    @abstractmethod
    def get_modified_files(self) -> List[str]:
        """Returns a list of relative paths for all files modified, created, or deleted."""
        pass

    @abstractmethod
    def apply_patch(self, patch_content: str) -> None:
        """Applies a unified patch to the workspace."""
        pass

    def __enter__(self) -> BaseEnvironment:
        self.setup()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cleanup()
