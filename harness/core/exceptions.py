"""Antigravity 하네스 시스템의 예외 클래스 정의 모듈.

에이전트 실행, 환경 격리, 가드레일 정책, 평가 등 각 계층에서 발생하는
에러를 명확히 분류하기 위한 예외 계층 구조를 제공합니다.
"""


class HarnessError(Exception):
    """하네스 시스템 전반에서 발생하는 모든 예외의 기본 클래스."""
    pass


# ============================================================================
# 실행기 및 프로세스 관련 예외 (Runner & Process Errors)
# ============================================================================

class RunnerError(HarnessError):
    """에이전트 실행기 실패 시 발생하는 기본 예외."""
    pass


class ProcessExecutionError(RunnerError):
    """외부 프로세스(예: agy CLI)가 0이 아닌 비정상 종료 코드로 종료되었을 때 발생."""

    def __init__(self, message: str, exit_code: int, stdout: str = "", stderr: str = ""):
        super().__init__(f"{message} (종료 코드: {exit_code})")
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class ProcessTimeoutError(RunnerError):
    """에이전트 실행이 설정된 제한 시간을 초과했을 때 발생."""

    def __init__(self, message: str, timeout_seconds: float):
        super().__init__(f"{message} (제한 시간: {timeout_seconds}초)")
        self.timeout_seconds = timeout_seconds


class StreamParseError(RunnerError):
    """NDJSON 또는 CLI 스트림 출력을 정상적으로 파싱할 수 없을 때 발생."""
    pass


# ============================================================================
# 워크스페이스 환경 관련 예외 (Environment & Workspace Errors)
# ============================================================================

class EnvironmentError(HarnessError):
    """워크스페이스 및 실행 환경 제어 실패 시 발생하는 기본 예외."""
    pass


class WorktreeError(EnvironmentError):
    """Git worktree 생성, diff 추출, 브랜치 정리 등 Git 연산 실패 시 발생."""
    pass


# ============================================================================
# 평가 및 검증 관련 예외 (Evaluation & Verification Errors)
# ============================================================================

class EvaluationError(HarnessError):
    """코드 변경사항 평가 및 검증 단계 실패 시 발생하는 기본 예외."""
    pass


class TestExecutionError(EvaluationError):
    """검증용 테스트 명령어 실행 자체가 실패하거나 비정상 중단되었을 때 발생."""
    pass


# ============================================================================
# 보안 가드레일 관련 예외 (Guardrail & Policy Errors)
# ============================================================================

class PolicyViolationError(HarnessError):
    """도구 실행이나 셸 명령어가 사전 정의된 보안 정책(SecurityPolicy)을 위반했을 때 발생."""
    pass
