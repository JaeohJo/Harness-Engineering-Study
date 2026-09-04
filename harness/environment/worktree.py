"""Git Worktree 기반의 고속 워크스페이스 격리 관리자 모듈.

호스트 Git 저장소의 메인 작업 트리를 오염시키지 않고, 태스크마다 독립적인 임시 브랜치와
Git Worktree를 동적으로 생성하여 완전한 샌드박싱과 고속 Diff 추출을 제공합니다.
"""

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
    """Git worktree를 사용하여 에이전트 전용 격리 워크스페이스를 제공하는 환경 관리자."""

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

        # 브랜치 및 작업 디렉터리 충돌 방지를 위한 유니크 ID 생성
        unique_id = uuid.uuid4().hex[:8]
        self.branch_name = f"harness/{task_id}-{unique_id}"

        if worktree_root:
            self.worktree_dir = Path(worktree_root).resolve() / f"wt-{task_id}-{unique_id}"
        else:
            self.worktree_dir = self.repo_path.parent / f".harness_wt_{task_id}_{unique_id}"

        self._is_setup = False

    @property
    def path(self) -> Path:
        """격리된 워크스페이스의 루트 경로를 반환합니다."""
        return self.worktree_dir

    def _run_git(self, args: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess[str]:
        """지정된 디렉터리(기본: 베이스 저장소)에서 Git 명령어를 실행합니다."""
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
            raise WorktreeError(f"Git 명령어 실행 실패 ('git {' '.join(args)}'): {error_msg}")

    def setup(self) -> Path:
        """Git worktree 및 임시 격리 브랜치를 생성하여 환경을 프로비저닝합니다."""
        if self._is_setup:
            return self.worktree_dir

        if not (self.repo_path / ".git").exists():
            raise WorktreeError(f"유효한 Git 저장소 경로가 아닙니다: {self.repo_path}")

        logger.debug(f"Git Worktree 생성: 경로='{self.worktree_dir}', 브랜치='{self.branch_name}'")
        self.worktree_dir.parent.mkdir(parents=True, exist_ok=True)

        try:
            # 베이스 커밋을 기준으로 신규 브랜치를 만들며 worktree 추가
            self._run_git([
                "worktree", "add",
                "-b", self.branch_name,
                str(self.worktree_dir),
                self.base_commit,
            ])
            self._is_setup = True
        except Exception as e:
            # 실패 시 부분 생성된 디렉터리 롤백
            if self.worktree_dir.exists():
                shutil.rmtree(self.worktree_dir, ignore_errors=True)
            raise WorktreeError(f"Git worktree 생성 중 실패: {e}")

        return self.worktree_dir

    def cleanup(self) -> None:
        """워크트리를 안전하게 제거하고 임시 브랜치를 삭제합니다."""
        if not self._is_setup and not self.worktree_dir.exists():
            return

        if not self.auto_cleanup:
            logger.info(f"디버깅을 위해 워크트리 정리를 건너뜁니다: {self.worktree_dir}")
            return

        logger.debug(f"워크트리 정리 중: 경로='{self.worktree_dir}', 브랜치='{self.branch_name}'")

        # 1. worktree 강제 제거
        try:
            self._run_git(["worktree", "remove", "--force", str(self.worktree_dir)])
        except Exception as e:
            logger.warning(f"git worktree remove 실패 ({e}). 파일시스템 직접 삭제 시도.")
            if self.worktree_dir.exists():
                shutil.rmtree(self.worktree_dir, ignore_errors=True)

        # 2. worktree 캐시 정리
        try:
            self._run_git(["worktree", "prune"])
        except Exception as e:
            logger.debug(f"worktree prune 알림: {e}")

        # 3. 임시 브랜치 삭제
        try:
            self._run_git(["branch", "-D", self.branch_name])
        except Exception as e:
            logger.debug(f"임시 브랜치 삭제 알림: {e}")

        self._is_setup = False

    def reset_baseline(self) -> None:
        """사전 파일 주입이나 설정 완료 후, 변경사항 측정의 기준선(baseline)을 현재 상태로 재설정합니다."""
        if not self.worktree_dir.exists():
            return
        try:
            subprocess.run(["git", "add", "-A"], cwd=str(self.worktree_dir), capture_output=True, check=False)
            status = self._run_git(
                ["status", "--porcelain", "--", ":(exclude).agents", ":(exclude)__pycache__"],
                cwd=self.worktree_dir,
            )
            if status.stdout.strip():
                self._run_git(["commit", "-m", "chore: setup initial files baseline"], cwd=self.worktree_dir)
        except Exception as e:
            logger.debug(f"reset_baseline 알림: {e}")

    def get_diff(self) -> str:
        """신규 생성된 파일(untracked)을 포함하여 변경된 전체 Unified Diff를 추출합니다."""
        if not self.worktree_dir.exists():
            return ""

        try:
            # 아직 git add 되지 않은 신규 파일도 diff에 잡히도록 intent-to-add 설정
            subprocess.run(
                ["git", "add", "-N", "."],
                cwd=str(self.worktree_dir),
                capture_output=True,
                check=False,
            )
            # HEAD 커밋 대비 모든 수정사항 추출 (.agents 및 __pycache__ 제외)
            res = self._run_git(
                ["diff", "HEAD", "--", ":(exclude).agents", ":(exclude)__pycache__"],
                cwd=self.worktree_dir,
            )
            return res.stdout
        except Exception as e:
            logger.error(f"Diff 추출 실패: {e}")
            return ""

    def get_modified_files(self) -> List[str]:
        """수정, 추가, 삭제된 파일의 상대 경로 목록을 반환합니다."""
        if not self.worktree_dir.exists():
            return []

        try:
            # git status 파싱
            res = self._run_git(["status", "--porcelain"], cwd=self.worktree_dir)
            files = []
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                # 포맷: 'XY filename'
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    filepath = parts[1].strip()
                    # 하네스 내부 가드레일 및 캐시 디렉터리 제외
                    if not (
                        filepath.startswith(".agents")
                        or filepath.startswith("__pycache__")
                        or "/__pycache__/" in filepath
                        or filepath.endswith(".pyc")
                    ):
                        files.append(filepath)
            return files
        except Exception as e:
            logger.error(f"수정 파일 목록 조회 실패: {e}")
            return []

    def apply_patch(self, patch_content: str) -> None:
        """Unified Diff 패치를 워크트리에 적용합니다."""
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
