"""Temporary directory environment for non-git or lightweight directory sandboxing."""

from __future__ import annotations

import difflib
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from harness.core.logging import logger
from harness.environment.base import BaseEnvironment


class LocalTempEnvironment(BaseEnvironment):
    """Provides a temporary filesystem sandbox by copying files and tracking changes."""

    def __init__(
        self,
        source_dir: Optional[str | Path] = None,
        task_id: str = "temp_task",
        auto_cleanup: bool = True,
    ):
        self.source_dir = Path(source_dir).resolve() if source_dir else None
        self.task_id = task_id
        self.auto_cleanup = auto_cleanup
        self._temp_dir: Optional[Path] = None
        self._initial_files: Dict[str, str] = {}

    @property
    def path(self) -> Path:
        if not self._temp_dir:
            raise RuntimeError("Environment has not been setup yet.")
        return self._temp_dir

    def _snapshot_files(self) -> Dict[str, str]:
        snapshot = {}
        if not self._temp_dir or not self._temp_dir.exists():
            return snapshot
        for file_path in self._temp_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(self._temp_dir).as_posix()
                try:
                    snapshot[rel_path] = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
        return snapshot

    def setup(self) -> Path:
        prefix = f"harness_{self.task_id}_"
        self._temp_dir = Path(tempfile.mkdtemp(prefix=prefix))

        if self.source_dir and self.source_dir.exists():
            shutil.copytree(self.source_dir, self._temp_dir, dirs_exist_ok=True)

        self._initial_files = self._snapshot_files()
        logger.debug(f"Created temp environment at '{self._temp_dir}' with {len(self._initial_files)} files")
        return self._temp_dir

    def cleanup(self) -> None:
        if self._temp_dir and self._temp_dir.exists() and self.auto_cleanup:
            logger.debug(f"Removing temp environment at '{self._temp_dir}'")
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None

    def get_diff(self) -> str:
        current_files = self._snapshot_files()
        all_keys = sorted(set(self._initial_files.keys()) | set(current_files.keys()))
        diff_lines: List[str] = []

        for key in all_keys:
            orig = self._initial_files.get(key, "").splitlines(keepends=True)
            curr = current_files.get(key, "").splitlines(keepends=True)
            file_diff = list(
                difflib.unified_diff(
                    orig,
                    curr,
                    fromfile=f"a/{key}",
                    tofile=f"b/{key}",
                )
            )
            if file_diff:
                diff_lines.extend(file_diff)

        return "".join(diff_lines)

    def get_modified_files(self) -> List[str]:
        current_files = self._snapshot_files()
        all_keys = set(self._initial_files.keys()) | set(current_files.keys())
        modified = []
        for key in sorted(all_keys):
            if key not in self._initial_files or key not in current_files:
                modified.append(key)
            elif self._initial_files[key] != current_files[key]:
                modified.append(key)
        return modified

    def apply_patch(self, patch_content: str) -> None:
        # Patch application for non-git environments can be done using patch tool if available
        if not patch_content.strip() or not self._temp_dir:
            return
        patch_file = self._temp_dir / ".temp_patch"
        try:
            patch_file.write_text(patch_content, encoding="utf-8")
            import subprocess
            subprocess.run(
                ["patch", "-p1", "-i", str(patch_file)],
                cwd=str(self._temp_dir),
                capture_output=True,
                check=False,
            )
        finally:
            if patch_file.exists():
                patch_file.unlink()
