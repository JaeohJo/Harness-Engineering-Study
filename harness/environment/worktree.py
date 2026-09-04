"""Git worktree-based environment for fast and isolated workspace provisioning."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path
from typing import List, Optional

from harness.core.exceptions import WorktreeError
from harness.core.logging import logger
from harness.environment.base import BaseEnvironment


class GitWorktreeEnvironment(BaseEnvironment):
    """Provides an isolated workspace using Git worktree, preventing changes to the main working tree."""

    def __init__(
        self,
        repo_path: str | Path,
        base_commit: str = "HEAD",
        task_id: str = "task",
        worktree_root: Optional[str | Path] = None,
        auto_cleanup: bool = True,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.base_commit = base_commit
        self.task_id = task_id
        self.auto_cleanup = auto_cleanup

        # Generate unique branch and worktree directory
        unique_id = uuid.uuid4().hex[:8]
        self.branch_name = f"harness/{task_id}-{unique_id}"

        if worktree_root:
            self.worktree_dir = Path(worktree_root).resolve() / f"wt-{task_id}-{unique_id}"
        else:
            self.worktree_dir = self.repo_path.parent / f".harness_wt_{task_id}_{unique_id}"

        self._is_setup = False

    @property
    def path(self) -> Path:
        """Returns the isolated workspace root path."""
        return self.worktree_dir

    def _run_git(self, args: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess[str]:
        """Runs a git command against either the base repo or the worktree."""
        target_dir = cwd or self.repo_path
        try:
            return subprocess.run(
                ["git"] + args,
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() or e.stdout.strip()
            raise WorktreeError(f"Git command failed: 'git {' '.join(args)}': {error_msg}")

    def setup(self) -> Path:
        """Creates the git worktree and temporary branch."""
        if self._is_setup:
            return self.worktree_dir

        if not (self.repo_path / ".git").exists():
            raise WorktreeError(f"Repository path is not a valid git repo: {self.repo_path}")

        logger.debug(f"Creating worktree at '{self.worktree_dir}' on branch '{self.branch_name}'")
        self.worktree_dir.parent.mkdir(parents=True, exist_ok=True)

        try:
            self._run_git([
                "worktree", "add",
                "-b", self.branch_name,
                str(self.worktree_dir),
                self.base_commit,
            ])
            self._is_setup = True
        except Exception as e:
            # Clean up partial directory if created
            if self.worktree_dir.exists():
                shutil.rmtree(self.worktree_dir, ignore_errors=True)
            raise WorktreeError(f"Failed to create git worktree: {e}")

        return self.worktree_dir

    def cleanup(self) -> None:
        """Removes the worktree and deletes the temporary branch."""
        if not self._is_setup and not self.worktree_dir.exists():
            return

        if not self.auto_cleanup:
            logger.info(f"Skipping worktree cleanup for debugging: {self.worktree_dir}")
            return

        logger.debug(f"Cleaning up worktree at '{self.worktree_dir}' and branch '{self.branch_name}'")
        try:
            self._run_git(["worktree", "remove", "--force", str(self.worktree_dir)])
        except Exception as e:
            logger.warning(f"Git worktree remove failed: {e}. Attempting manual removal.")
            if self.worktree_dir.exists():
                shutil.rmtree(self.worktree_dir, ignore_errors=True)

        try:
            self._run_git(["worktree", "prune"])
        except Exception as e:
            logger.debug(f"Git worktree prune notice: {e}")

        try:
            self._run_git(["branch", "-D", self.branch_name])
        except Exception as e:
            logger.debug(f"Git branch delete notice: {e}")

        self._is_setup = False

    def get_diff(self) -> str:
        """Captures unified diff of all changes made in the worktree (including untracked files)."""
        if not self.worktree_dir.exists():
            return ""

        # Include untracked files in the diff by marking them with intent-to-add
        try:
            subprocess.run(
                ["git", "add", "-N", "."],
                cwd=str(self.worktree_dir),
                capture_output=True,
                check=False,
            )
            res = self._run_git(["diff", "HEAD"], cwd=self.worktree_dir)
            return res.stdout
        except Exception as e:
            logger.error(f"Failed to get diff: {e}")
            return ""

    def get_modified_files(self) -> List[str]:
        """Returns list of all changed, added, or deleted files."""
        if not self.worktree_dir.exists():
            return []

        try:
            res = self._run_git(["status", "--porcelain"], cwd=self.worktree_dir)
            files = []
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                # Line format is 'XY filename'
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    files.append(parts[1].strip())
            return files
        except Exception as e:
            logger.error(f"Failed to retrieve modified files: {e}")
            return []

    def apply_patch(self, patch_content: str) -> None:
        """Applies a patch cleanly to the worktree."""
        if not patch_content.strip():
            return

        patch_file = self.worktree_dir / ".harness_patch.tmp"
        try:
            patch_file.write_text(patch_content, encoding="utf-8")
            self._run_git(
                ["apply", "--whitespace=nowarn", str(patch_file)],
                cwd=self.worktree_dir,
            )
        finally:
            if patch_file.exists():
                patch_file.unlink()
