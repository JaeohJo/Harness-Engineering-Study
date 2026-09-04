"""Core exceptions for the Antigravity Harness system."""

class HarnessError(Exception):
    """Base exception for all harness-related errors."""
    pass


# Runner & Process Errors
class RunnerError(HarnessError):
    """Base exception for runner failures."""
    pass


class ProcessExecutionError(RunnerError):
    """Raised when an external process (e.g. agy CLI) exits with a non-zero code unexpectedly."""
    def __init__(self, message: str, exit_code: int, stdout: str = "", stderr: str = ""):
        super().__init__(f"{message} (exit code: {exit_code})")
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class ProcessTimeoutError(RunnerError):
    """Raised when an execution exceeds its allotted time limit."""
    def __init__(self, message: str, timeout_seconds: float):
        super().__init__(f"{message} (timeout: {timeout_seconds}s)")
        self.timeout_seconds = timeout_seconds


class StreamParseError(RunnerError):
    """Raised when an NDJSON or stream output cannot be parsed."""
    pass


# Environment & Workspace Errors
class EnvironmentError(HarnessError):
    """Base exception for workspace/environment failures."""
    pass


class WorktreeError(EnvironmentError):
    """Raised when a Git worktree operation fails."""
    pass


# Evaluation & Verification Errors
class EvaluationError(HarnessError):
    """Base exception for evaluation failures."""
    pass


class TestExecutionError(EvaluationError):
    """Raised when evaluation test command fails to execute."""
    pass


# Guardrail & Policy Errors
class PolicyViolationError(HarnessError):
    """Raised when a tool execution or command violates a safety policy."""
    pass
