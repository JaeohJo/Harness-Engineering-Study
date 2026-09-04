"""테스트 스위트 실행 및 최종 통과 여부 판정 평가기 모듈.

태스크에 정의된 검증 패치(test_patch)를 적용하고, 지정된 테스트 명령어(pytest 등)를 실행하여
표준 출력 및 에러를 파싱함으로써 통과/실패/에러 여부를 종합 판정합니다.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import List, Optional

from harness.core.logging import logger
from harness.core.models import EvalResult, EvalStatus, TaskSpec
from harness.evaluator.base import BaseEvaluator
from harness.evaluator.diff_evaluator import DiffEvaluator


class TestEvaluator(BaseEvaluator):
    """검증용 테스트 스위트를 실행하여 에이전트 수정본의 유효성을 평가하는 평가기."""
    __test__ = False  # pytest 수집 대상에서 제외

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
        """태스크의 성공 여부를 정적 검사 및 테스트 실행을 통해 다단계로 검증합니다.

        평가 파이프라인:
        1단계: Diff에 대한 AST 문법 에러 및 수정 금지 파일 위반 여부 검증
        2단계: 검증용 골든 테스트 패치(test_patch) 적용
        3단계: 테스트 명령어 실행 (타임아웃 적용)
        4단계: 테스트 결과 파싱 및 PASS/FAIL/ERROR 상태 판정
        """
        start_time = time.time()
        workspace = Path(workspace_dir).resolve()

        # 1. 변경사항 정적 검사 (구문 오류 및 정책 위반 감지)
        diff_analysis = None
        if diff:
            forbidden = task.metadata.get("forbidden_paths") if task.metadata else None
            diff_analysis = self.diff_evaluator.analyze(diff, workspace, forbidden_paths=forbidden)

            # 파이썬 구문 에러가 있는 경우 테스트 실행 전 즉시 ERROR 반환
            if not diff_analysis.is_valid_syntax:
                duration = time.time() - start_time
                return EvalResult(
                    task_id=task.task_id,
                    status=EvalStatus.ERROR,
                    diff=diff,
                    message=f"수정된 파일에서 문법 에러가 발견되었습니다: {diff_analysis.syntax_errors}",
                    duration_seconds=duration,
                    details={"diff_analysis": diff_analysis.to_dict()},
                )

            # 수정 금지된 파일을 건드린 경우 FAIL 처리
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

        # 2. 테스트 전용 패치가 지정된 경우 워크스페이스에 적용
        if task.test_patch and task.test_patch.strip():
            logger.debug(f"태스크 '{task.task_id}' 테스트 패치 적용 중")
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
                    message=f"평가용 테스트 패치 적용 실패: {e}",
                    duration_seconds=duration,
                )
            finally:
                if patch_file.exists():
                    patch_file.unlink()

        # 3. 테스트 명령어 실행
        cmd_str = task.test_command or self.default_test_command
        logger.debug(f"평가 테스트 명령어 실행: '{cmd_str}' (작업 디렉터리: '{workspace}')")

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
            stderr = f"테스트 실행 시간이 초과되었습니다 ({self.test_timeout_seconds}초)"
            exit_code = -1
            timed_out = True

        duration = time.time() - start_time

        # 타임아웃 발생 시 결과
        if timed_out:
            return EvalResult(
                task_id=task.task_id,
                status=EvalStatus.TIMEOUT,
                diff=diff or "",
                message=stderr,
                duration_seconds=duration,
                details={"stdout": stdout, "stderr": stderr},
            )

        # 4. 테스트 결과 문자열 파싱
        passed_tests, failed_tests, errored_tests = self._parse_test_output(stdout, stderr)

        status = EvalStatus.PASS if exit_code == 0 else EvalStatus.FAIL
        message = (
            f"테스트 통과 ({len(passed_tests)}건 통과, {len(failed_tests)}건 실패)"
            if status == EvalStatus.PASS
            else f"테스트 실패 (종료 코드 {exit_code}, {len(failed_tests)}건 실패)"
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
        """pytest 및 unittest 형식의 출력 문자열에서 통과/실패한 개별 테스트 이름을 추출합니다."""
        combined = f"{stdout}\n{stderr}"
        passed = []
        failed = []
        errored = []

        for line in combined.splitlines():
            line_str = line.strip()
            # Pytest 표준 출력 포맷 (예: test_add.py::test_case PASSED)
            if " PASSED" in line_str:
                passed.append(line_str.replace(" PASSED", "").strip())
            elif " FAILED" in line_str:
                failed.append(line_str.replace(" FAILED", "").strip())
            elif " ERROR" in line_str:
                errored.append(line_str.replace(" ERROR", "").strip())
            # Python unittest 표준 출력 포맷 (예: test_case ... ok)
            elif line_str.endswith("... ok"):
                passed.append(line_str.replace("... ok", "").strip())
            elif line_str.endswith("... FAIL"):
                failed.append(line_str.replace("... FAIL", "").strip())
            elif line_str.endswith("... ERROR"):
                errored.append(line_str.replace("... ERROR", "").strip())

        return passed, failed, errored
