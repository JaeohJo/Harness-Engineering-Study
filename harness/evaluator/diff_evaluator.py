"""에이전트가 생성한 Diff 분석 및 AST 문법 검증기 모듈.

Unified Diff를 파싱하여 추가/삭제 라인 수, 변경된 파일 목록을 추출하고,
수정된 파이썬 파일들에 대해 ast.parse를 수행하여 문법 오류(SyntaxError)를 사전에 포착합니다.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Optional

from harness.core.logging import logger


class DiffAnalysisResult:
    """코드 변경사항에 대한 정적/구조적 분석 결과 객체."""

    def __init__(self):
        self.lines_added: int = 0
        self.lines_removed: int = 0
        self.files_modified: List[str] = []
        self.syntax_errors: Dict[str, str] = {}
        self.is_valid_syntax: bool = True
        self.policy_violations: List[str] = []

    def to_dict(self) -> dict:
        return {
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "files_modified": self.files_modified,
            "syntax_errors": self.syntax_errors,
            "is_valid_syntax": self.is_valid_syntax,
            "policy_violations": self.policy_violations,
        }


class DiffEvaluator:
    """Unified Diff를 분석하여 통계를 산출하고, 금지된 경로 수정 및 문법 에러를 검증합니다."""

    def analyze(
        self,
        diff_text: str,
        workspace_dir: str | Path,
        forbidden_paths: Optional[List[str]] = None,
    ) -> DiffAnalysisResult:
        """Diff 텍스트와 워크스페이스를 바탕으로 코드 변경사항을 정밀 분석합니다."""
        result = DiffAnalysisResult()
        workspace = Path(workspace_dir).resolve()

        if not diff_text.strip():
            return result

        # 1. Diff 라인 파싱 (수정된 파일 및 라인 수 계산)
        current_file: Optional[str] = None
        for line in diff_text.splitlines():
            if line.startswith("+++ b/"):
                current_file = line[6:].strip()
                if current_file not in result.files_modified:
                    result.files_modified.append(current_file)
            elif line.startswith("+") and not line.startswith("+++"):
                result.lines_added += 1
            elif line.startswith("-") and not line.startswith("---"):
                result.lines_removed += 1

        # 2. 금지된 파일 수정 여부 검사 (Scope Creep 방지)
        if forbidden_paths:
            for mod_file in result.files_modified:
                for forbidden in forbidden_paths:
                    if forbidden in mod_file:
                        result.policy_violations.append(
                            f"수정이 금지된 경로 '{mod_file}'(패턴 '{forbidden}')가 변경되었습니다."
                        )

        # 3. 변경된 Python 소스코드의 AST 구문 검사
        for mod_file in result.files_modified:
            if mod_file.endswith(".py"):
                abs_path = workspace / mod_file
                if abs_path.exists() and abs_path.is_file():
                    try:
                        content = abs_path.read_text(encoding="utf-8", errors="replace")
                        # 구문 트리 파싱 시도
                        ast.parse(content, filename=str(abs_path))
                    except SyntaxError as syn_err:
                        err_msg = f"문법 에러 (라인 {syn_err.lineno}): {syn_err.msg}"
                        result.syntax_errors[mod_file] = err_msg
                        result.is_valid_syntax = False
                        logger.warning(f"{mod_file} 파일에서 AST 구문 에러 발견: {err_msg}")
                    except Exception as err:
                        result.syntax_errors[mod_file] = str(err)
                        result.is_valid_syntax = False

        return result
