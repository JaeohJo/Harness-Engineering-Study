"""Diff analyzer and syntax validator for code changes produced by the agent."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Optional

from harness.core.logging import logger


class DiffAnalysisResult:
    """Detailed structural analysis of code modifications."""

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
    """Analyzes unified diffs, counts changes, and validates syntax on modified files."""

    def analyze(
        self,
        diff_text: str,
        workspace_dir: str | Path,
        forbidden_paths: Optional[List[str]] = None,
    ) -> DiffAnalysisResult:
        result = DiffAnalysisResult()
        workspace = Path(workspace_dir).resolve()

        if not diff_text.strip():
            return result

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

        # Check forbidden paths
        if forbidden_paths:
            for mod_file in result.files_modified:
                for forbidden in forbidden_paths:
                    if forbidden in mod_file:
                        result.policy_violations.append(
                            f"Agent modified forbidden path '{mod_file}' matching '{forbidden}'"
                        )

        # Syntax check modified Python files
        for mod_file in result.files_modified:
            if mod_file.endswith(".py"):
                abs_path = workspace / mod_file
                if abs_path.exists() and abs_path.is_file():
                    try:
                        content = abs_path.read_text(encoding="utf-8", errors="replace")
                        ast.parse(content, filename=str(abs_path))
                    except SyntaxError as syn_err:
                        err_msg = f"SyntaxError on line {syn_err.lineno}: {syn_err.msg}"
                        result.syntax_errors[mod_file] = err_msg
                        result.is_valid_syntax = False
                        logger.warning(f"AST Syntax error in {mod_file}: {err_msg}")
                    except Exception as err:
                        result.syntax_errors[mod_file] = str(err)
                        result.is_valid_syntax = False

        return result
