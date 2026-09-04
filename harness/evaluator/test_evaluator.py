"""Test execution and test-suite outcome evaluator."""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import List, Optional

from harness.core.logging import logger
from harness.core.models import EvalResult, EvalStatus, TaskSpec
from harness.evaluator.base import BaseEvaluator
from harness.evaluator.diff_evaluator import DiffEvaluator


class TestEvaluator(BaseEvaluator):
    """Executes verification tests and assesses the correctness of agent solutions."""
    __test__ = False

    def __init__(
        self,
        default_test_command: str = "pytest",
        test_timeout_seconds: float = 120.0,
    ):
        self.default_test_command = default_test_command
        self.test_timeout_seconds = test_timeout_seconds
        self.diff_evaluator = DiffEvaluator()

    def evaluate(
        self,
        workspace_dir: str | Path,
        task: TaskSpec,
        diff: Optional[str] = None,
        **kwargs,
    ) -> EvalResult:
        start_time = time.time()
        workspace = Path(workspace_dir).resolve()

        # 1. Structural & syntax validation on diff
        diff_analysis = None
        if diff:
            forbidden = task.metadata.get("forbidden_paths") if task.metadata else None
            diff_analysis = self.diff_evaluator.analyze(diff, workspace, forbidden_paths=forbidden)

            if not diff_analysis.is_valid_syntax:
                duration = time.time() - start_time
                return EvalResult(
                    task_id=task.task_id,
                    status=EvalStatus.ERROR,
                    diff=diff,
                    message=f"Syntax validation failed on modified files: {diff_analysis.syntax_errors}",
                    duration_seconds=duration,
                    details={"diff_analysis": diff_analysis.to_dict()},
                )

            if diff_analysis.policy_violations:
                duration = time.time() - start_time
                return EvalResult(
                    task_id=task.task_id,
                    status=EvalStatus.FAIL,
                    diff=diff,
                    message="; ".join(diff_analysis.policy_violations),
                    duration_seconds=duration,
                    details={"diff_analysis": diff_analysis.to_dict()},
                )

        # 2. Apply test patch if provided
        if task.test_patch and task.test_patch.strip():
            logger.debug(f"Applying test patch for task '{task.task_id}'")
            patch_file = workspace / ".eval_test_patch.tmp"
            try:
                patch_file.write_text(task.test_patch, encoding="utf-8")
                subprocess.run(
                    ["git", "apply", "--whitespace=nowarn", str(patch_file)],
                    cwd=str(workspace),
                    capture_output=True,
                    check=True,
                )
            except Exception as e:
                duration = time.time() - start_time
                return EvalResult(
                    task_id=task.task_id,
                    status=EvalStatus.ERROR,
                    diff=diff or "",
                    message=f"Failed to apply evaluation test patch: {e}",
                    duration_seconds=duration,
                )
            finally:
                if patch_file.exists():
                    patch_file.unlink()

        # 3. Determine test command
        cmd_str = task.test_command or self.default_test_command
        logger.debug(f"Running evaluation test command: '{cmd_str}' in '{workspace}'")

        try:
            res = subprocess.run(
                cmd_str,
                shell=True,
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=self.test_timeout_seconds,
            )
            stdout = res.stdout
            stderr = res.stderr
            exit_code = res.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            stdout = ""
            stderr = f"Test execution timed out after {self.test_timeout_seconds} seconds"
            exit_code = -1
            timed_out = True

        duration = time.time() - start_time

        if timed_out:
            return EvalResult(
                task_id=task.task_id,
                status=EvalStatus.TIMEOUT,
                diff=diff or "",
                message=stderr,
                duration_seconds=duration,
                details={"stdout": stdout, "stderr": stderr},
            )

        # 4. Parse test results
        passed_tests, failed_tests, errored_tests = self._parse_test_output(stdout, stderr)

        status = EvalStatus.PASS if exit_code == 0 else EvalStatus.FAIL
        message = (
            f"Tests passed ({len(passed_tests)} passed, {len(failed_tests)} failed)"
            if status == EvalStatus.PASS
            else f"Tests failed with exit code {exit_code} ({len(failed_tests)} failed)"
        )

        return EvalResult(
            task_id=task.task_id,
            status=status,
            tests_passed=passed_tests,
            tests_failed=failed_tests,
            tests_errored=errored_tests,
            diff=diff or "",
            message=message,
            duration_seconds=duration,
            details={
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "diff_analysis": diff_analysis.to_dict() if diff_analysis else {},
            },
        )

    def _parse_test_output(self, stdout: str, stderr: str) -> tuple[List[str], List[str], List[str]]:
        """Extracts passed, failed, and errored test names from stdout/stderr."""
        combined = f"{stdout}\n{stderr}"
        passed = []
        failed = []
        errored = []

        for line in combined.splitlines():
            line_str = line.strip()
            # Pytest format: test_name PASSED / FAILED / ERROR
            if " PASSED" in line_str:
                passed.append(line_str.replace(" PASSED", "").strip())
            elif " FAILED" in line_str:
                failed.append(line_str.replace(" FAILED", "").strip())
            elif " ERROR" in line_str:
                errored.append(line_str.replace(" ERROR", "").strip())
            # Unittest format: ok / FAIL / ERROR
            elif line_str.endswith("... ok"):
                passed.append(line_str.replace("... ok", "").strip())
            elif line_str.endswith("... FAIL"):
                failed.append(line_str.replace("... FAIL", "").strip())
            elif line_str.endswith("... ERROR"):
                errored.append(line_str.replace("... ERROR", "").strip())

        return passed, failed, errored
