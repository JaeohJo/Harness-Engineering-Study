"""End-to-end unit tests for TaskDataset, HarnessEngine, and CLI interface."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from harness.benchmark.dataset import TaskDataset
from harness.benchmark.engine import HarnessEngine
from harness.core.config import HarnessConfig
from harness.core.models import (
    EvalStatus,
    ExecutionResult,
    TaskSpec,
)
from harness.runner.base import BaseRunner


def test_dataset_json_and_jsonl_io(tmp_path: Path):
    tasks = [
        TaskSpec(task_id="task_1", description="Fix issue 1"),
        TaskSpec(task_id="task_2", description="Fix issue 2"),
    ]
    dataset = TaskDataset(tasks)

    # Test JSON save/load
    json_path = tmp_path / "tasks.json"
    dataset.save(json_path)
    loaded_json = TaskDataset.load(json_path)
    assert len(loaded_json) == 2
    assert loaded_json.tasks[0].task_id == "task_1"

    # Test JSONL save/load
    jsonl_path = tmp_path / "tasks.jsonl"
    dataset.save(jsonl_path)
    loaded_jsonl = TaskDataset.load(jsonl_path)
    assert len(loaded_jsonl) == 2
    assert loaded_jsonl.tasks[1].task_id == "task_2"


@pytest.mark.asyncio
async def test_harness_engine_lifecycle(tmp_path: Path):
    # Setup mock workspace files
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    code_file = src_dir / "math_ops.py"
    code_file.write_text("def sub(a, b): return a + b\n")

    task = TaskSpec(
        task_id="task_test_fix",
        description="Fix sub in math_ops.py",
        repo_path=str(src_dir),
        test_command="python3 -c 'import math_ops; assert math_ops.sub(5, 2) == 3'",
    )

    # Create mock runner that simulates fixing the bug
    mock_runner = MagicMock(spec=BaseRunner)

    async def fake_run(*args, **kwargs):
        workspace = Path(kwargs.get("workspace_dir") or args[1])
        # Agent performs file edit in workspace
        (workspace / "math_ops.py").write_text("def sub(a, b): return a - b\n")
        return ExecutionResult(
            task_id="task_test_fix",
            exit_code=0,
            conversation_id="conv_123",
            final_response="Fixed subtraction",
        )

    mock_runner.run = AsyncMock(side_effect=fake_run)

    config = HarnessConfig(cleanup_worktree=True, output_dir=tmp_path / "reports")
    engine = HarnessEngine(config=config, runner=mock_runner)

    exec_res, eval_res, telem = await engine.run_task(task)

    assert exec_res.is_success
    assert eval_res.status == EvalStatus.PASS
    assert "+def sub(a, b): return a - b" in eval_res.diff
    assert telem.task_id == "task_test_fix"


@pytest.mark.asyncio
async def test_harness_benchmark_run(tmp_path: Path):
    dataset = TaskDataset([
        TaskSpec(task_id="task_a", description="Task A", test_command="python3 -c 'assert True'"),
        TaskSpec(task_id="task_b", description="Task B", test_command="python3 -c 'assert False'"),
    ])

    mock_runner = MagicMock(spec=BaseRunner)
    mock_runner.run = AsyncMock(return_value=ExecutionResult(task_id="test", exit_code=0))

    output_dir = tmp_path / "bench_reports"
    engine = HarnessEngine(config=HarnessConfig(cleanup_worktree=True), runner=mock_runner)

    report = await engine.run_benchmark(dataset=dataset, output_dir=output_dir)

    assert report.total_tasks == 2
    assert report.passed_tasks == 1
    assert report.failed_tasks == 1
    assert report.pass_rate == 50.0
    assert (output_dir / "benchmark_report.json").exists()
    assert (output_dir / "benchmark_report.md").exists()


@pytest.mark.asyncio
async def test_harness_engine_with_initial_files(tmp_path: Path):
    task = TaskSpec(
        task_id="standalone_task",
        description="Fix sub in calc.py",
        initial_files={"calc.py": "def sub(a, b): return a + b\n"},
        test_command="python3 -c 'import calc; assert calc.sub(5, 2) == 3'",
    )

    mock_runner = MagicMock(spec=BaseRunner)

    async def fake_run(*args, **kwargs):
        workspace = Path(kwargs.get("workspace_dir") or args[1])
        # Verify initial_files were populated before runner starts
        assert (workspace / "calc.py").exists()
        assert "def sub(a, b): return a + b" in (workspace / "calc.py").read_text()
        # Simulate agent fix
        (workspace / "calc.py").write_text("def sub(a, b): return a - b\n")
        return ExecutionResult(task_id="standalone_task", exit_code=0)

    mock_runner.run = AsyncMock(side_effect=fake_run)
    engine = HarnessEngine(runner=mock_runner)
    exec_res, eval_res, telem = await engine.run_task(task)

    assert eval_res.status == EvalStatus.PASS
    assert telem.lines_added > 0
    assert telem.lines_removed > 0
