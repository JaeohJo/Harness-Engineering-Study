"""비Git 환경 및 경량 샌드박스를 위한 임시 디렉터리 환경 관리자 모듈.

Git 저장소가 아닌 일반 소스코드 폴더를 임시 디렉터리로 복제하고,
실행 전후 파일 스냅샷을 비교하여 Diff 및 수정 목록을 산출합니다.
"""

from __future__ import annotations

import difflib
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from harness.core.logging import logger
from harness.environment.base import BaseEnvironment


class LocalTempEnvironment(BaseEnvironment):
    """임시 디렉터리 복사 및 파일 변경 비교 기반의 샌드박스 환경 관리자."""

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
            raise RuntimeError("환경이 아직 초기화(setup)되지 않았습니다.")
        return self._temp_dir

    def _snapshot_files(self) -> Dict[str, str]:
        """현재 디렉터리의 모든 파일 내용을 상대 경로와 함께 스냅샷합니다."""
        snapshot = {}
        if not self._temp_dir or not self._temp_dir.exists():
            return snapshot
        for file_path in self._temp_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(self._temp_dir).as_posix()
                # 하네스 내부 가드레일(.agents) 및 파이썬 캐시 제외
                if (
                    rel_path.startswith(".agents")
                    or rel_path.startswith("__pycache__")
                    or "/__pycache__/" in rel_path
                    or rel_path.endswith(".pyc")
                ):
                    continue
                try:
                    snapshot[rel_path] = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
        return snapshot

    def reset_baseline(self) -> None:
        """사전 파일 주입이나 설정 완료 후, 변경사항 측정의 기준선(baseline)을 현재 상태로 재설정합니다."""
        self._initial_files = self._snapshot_files()

    def setup(self) -> Path:
        """독립된 임시 디렉터리를 생성하고 원본 소스코드를 복제합니다."""
        prefix = f"harness_{self.task_id}_"
        self._temp_dir = Path(tempfile.mkdtemp(prefix=prefix))

        if self.source_dir and self.source_dir.exists():
            shutil.copytree(self.source_dir, self._temp_dir, dirs_exist_ok=True)

        # 초기 상태 파일 스냅샷 기록
        self._initial_files = self._snapshot_files()
        logger.debug(f"임시 샌드박스 생성 완료: '{self._temp_dir}' (초기 파일 {len(self._initial_files)}개)")
        return self._temp_dir

    def cleanup(self) -> None:
        """임시 디렉터리 전체를 삭제합니다."""
        if self._temp_dir and self._temp_dir.exists() and self.auto_cleanup:
            logger.debug(f"임시 샌드박스 삭제: '{self._temp_dir}'")
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None

    def get_diff(self) -> str:
        """초기 스냅샷과 현재 파일들을 비교하여 Unified Diff를 생성합니다."""
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
        """변경된 파일 상대 경로 목록을 반환합니다."""
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
        """patch 명령어를 사용하여 임시 샌드박스에 패치를 적용합니다."""
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
