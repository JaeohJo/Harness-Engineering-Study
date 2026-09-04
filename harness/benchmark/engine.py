"""End-to-end benchmark orchestration engine for Antigravity CLI."""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional

from harness.benchmark.dataset import TaskDataset
from harness.core.config import HarnessConfig, RunnerConfig
from harness.core.logging import logger, console
from harness.core.models import (
    EvalResult,
    EvalStatus,
    ExecutionResult,
    TaskSpec,
    TelemetryData,
)
from harness.environment.base import BaseEnvironment
from harness.environment.temp_dir import LocalTempEnvironment
from harness.environment.worktree import GitWorktreeEnvironment
from harness.evaluator.base import BaseEvaluator
from harness.evaluator.test_evaluator import TestEvaluator
from harness.guardrails.hooks import HookManager
from harness.runner.base import BaseRunner
from harness.runner.cli_runner import CliRunner
from harness.telemetry.reporter import BenchmarkReport
from harness.telemetry.transcript import TranscriptParser


class HarnessEngine:
    """Orchestrates task provisioning, agent execution, guardrail monitoring, and evaluation."""

    def __init__(
        self,
        config: Optional[HarnessConfig] = None,
        runner: Optional[BaseRunner] = None,
        evaluator: Optional[BaseEvaluator] = None,
        hook_manager: Optional[HookManager] = None,
        transcript_parser: Optional[TranscriptParser] = None,
    ):
        self.config = config or HarnessConfig()
        self.runner = runner or CliRunner(self.config.runner)
        self.evaluator = evaluator or TestEvaluator()
        self.hook_manager = hook_manager or HookManager()
        self.transcript_parser = transcript_parser or TranscriptParser()

    def _create_environment(self, task: TaskSpec) -> BaseEnvironment:
        """Determines and constructs the appropriate isolated environment for a task."""
        repo_path = Path(task.repo_path).resolve() if task.repo_path else None

        if repo_path and (repo_path / ".git").exists():
            return GitWorktreeEnvironment(
                repo_path=repo_path,
                base_commit=task.base_commit or "HEAD",
                task_id=task.task_id,
                auto_cleanup=self.config.cleanup_worktree,
            )
        else:
            return LocalTempEnvironment(
                source_dir=repo_path,
                task_id=task.task_id,
                auto_cleanup=self.config.cleanup_worktree,
            )

    async def run_task(
        self,
        task: TaskSpec,
    ) -> tuple[ExecutionResult, EvalResult, TelemetryData]:
        """Runs the entire end-to-end harness lifecycle for a single task."""
        logger.info(f"Starting execution for task: [bold cyan]{task.task_id}[/bold cyan]")
        start_time = time.time()

        env = self._create_environment(task)
        workspace_path = env.setup()

        try:
            # 1. Inject guardrails if enabled
            if self.config.enable_guardrails:
                self.hook_manager.inject_hooks(workspace_path)

            # 2. Run the agent
            exec_res = await self.runner.run(
                prompt=task.description,
                workspace_dir=str(workspace_path),
                task_id=task.task_id,
            )

            # 3. Extract diff
            diff = env.get_diff()

            # 4. Evaluate correctness
            eval_res = self.evaluator.evaluate(
                workspace_dir=workspace_path,
                task=task,
                diff=diff,
            )

            # 5. Extract telemetry
            telemetry = self.transcript_parser.extract_telemetry(
                task_id=task.task_id,
                conversation_id=exec_res.conversation_id,
                duration_seconds=time.time() - start_time,
            )
            telemetry.files_modified = env.get_modified_files()

            logger.info(
                f"Completed task [bold cyan]{task.task_id}[/bold cyan]: "
                f"Status=[bold {'green' if eval_res.status == EvalStatus.PASS else 'red'}]{eval_res.status.value}[/] "
                f"in {eval_res.duration_seconds:.1f}s"
            )

            return exec_res, eval_res, telemetry

        finally:
            if self.config.cleanup_worktree:
                env.cleanup()

    async def run_benchmark(
        self,
        dataset: TaskDataset,
        output_dir: Optional[Path | str] = None,
    ) -> BenchmarkReport:
        """Executes a benchmark suite across all tasks in a dataset and outputs reports."""
        out_dir = Path(output_dir or self.config.output_dir)
        exec_results: List[ExecutionResult] = []
        eval_results: List[EvalResult] = []
        telemetries: List[TelemetryData] = []

        logger.info(f"Launching benchmark for [bold yellow]{len(dataset)}[/bold yellow] tasks...")

        for task in dataset:
            try:
                exec_res, eval_res, telem = await self.run_task(task)
                exec_results.append(exec_res)
                eval_results.append(eval_res)
                telemetries.append(telem)
            except Exception as e:
                logger.error(f"Task '{task.task_id}' crashed with unexpected exception: {e}")
                eval_results.append(
                    EvalResult(
                        task_id=task.task_id,
                        status=EvalStatus.ERROR,
                        message=f"Harness exception: {e}",
                    )
                )

        report = BenchmarkReport(
            eval_results=eval_results,
            exec_results=exec_results,
            telemetry_data=telemetries,
            model_name=self.config.runner.model or "default_model",
        )

        json_path, md_path = report.save(out_dir)
        logger.info(f"Benchmark finished! Reports saved to:\n- {md_path}\n- {json_path}")

        return report
