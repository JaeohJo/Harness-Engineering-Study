"""Unit tests for DiffEvaluator and TestEvaluator."""

from pathlib import Path
import pytest

from harness.core.models import EvalStatus, TaskSpec
from harness.evaluator.diff_evaluator import DiffEvaluator
from harness.evaluator.test_evaluator import TestEvaluator


def test_diff_evaluator_valid_syntax(tmp_path: Path):
    evaluator = DiffEvaluator()

    py_file = tmp_path / "solution.py"
    py_file.write_text("def solve():\n    return 42\n")

    diff_text = (
        "--- a/solution.py\n"
        "+++ b/solution.py\n"
        "@@ -1,1 +1,2 @@\n"
        "-def solve():\n"
        "-    pass\n"
        "+def solve():\n"
        "+    return 42\n"
    )

    result = evaluator.analyze(diff_text, tmp_path)
    assert result.is_valid_syntax is True
    assert "solution.py" in result.files_modified
    assert result.lines_added == 2
    assert result.lines_removed == 2
    assert len(result.syntax_errors) == 0


def test_diff_evaluator_syntax_error(tmp_path: Path):
    evaluator = DiffEvaluator()

    py_file = tmp_path / "broken.py"
    py_file.write_text("def solve(:\n    broken syntax\n")

    diff_text = (
        "--- a/broken.py\n"
        "+++ b/broken.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+def solve(:\n"
        "+    broken syntax\n"
    )

    result = evaluator.analyze(diff_text, tmp_path)
    assert result.is_valid_syntax is False
    assert "broken.py" in result.syntax_errors


def test_diff_evaluator_forbidden_path(tmp_path: Path):
    evaluator = DiffEvaluator()
    diff_text = "+++ b/secret/credentials.json\n+key=123\n"

    result = evaluator.analyze(diff_text, tmp_path, forbidden_paths=["secret/"])
    assert len(result.policy_violations) == 1
    assert "credentials.json" in result.policy_violations[0]


def test_test_evaluator_pass(tmp_path: Path):
    evaluator = TestEvaluator()
    task = TaskSpec(
        task_id="t1",
        description="Verify addition",
        test_command="python3 -c 'assert 1 + 1 == 2'",
    )

    result = evaluator.evaluate(workspace_dir=tmp_path, task=task)
    assert result.status == EvalStatus.PASS
    assert result.details["exit_code"] == 0


def test_test_evaluator_fail(tmp_path: Path):
    evaluator = TestEvaluator()
    task = TaskSpec(
        task_id="t2",
        description="Verify failure",
        test_command="python3 -c 'assert 1 == 0'",
    )

    result = evaluator.evaluate(workspace_dir=tmp_path, task=task)
    assert result.status == EvalStatus.FAIL
    assert result.details["exit_code"] != 0
