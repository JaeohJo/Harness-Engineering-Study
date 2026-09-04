"""Command-line interface for Antigravity Harness."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from rich.panel import Panel
from rich.table import Table

from harness.benchmark.dataset import TaskDataset
from harness.benchmark.engine import HarnessEngine
from harness.core.config import HarnessConfig, RunnerConfig
from harness.core.logging import console
from harness.core.models import EvalStatus, TaskSpec


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agy-harness",
        description="Production-grade Harness Engineering framework for Antigravity CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Run a single task through the harness")
    run_parser.add_argument("--task", "-t", required=True, help="Path to task JSON file")
    run_parser.add_argument("--config", "-c", help="Path to harness.yaml configuration")
    run_parser.add_argument("--model", "-m", help="Override agent model")
    run_parser.add_argument("--effort", choices=["low", "medium", "high"], help="Reasoning effort")
    run_parser.add_argument("--timeout", type=float, help="Timeout in seconds")
    run_parser.add_argument("--keep-workspace", action="store_true", help="Do not cleanup isolated workspace")

    # Command: benchmark
    bench_parser = subparsers.add_parser("benchmark", help="Run an evaluation benchmark across a dataset")
    bench_parser.add_argument("--dataset", "-d", required=True, help="Path to dataset JSON or JSONL file")
    bench_parser.add_argument("--output", "-o", default="reports", help="Output directory for reports")
    bench_parser.add_argument("--config", "-c", help="Path to harness.yaml configuration")
    bench_parser.add_argument("--model", "-m", help="Override agent model")
    bench_parser.add_argument("--effort", choices=["low", "medium", "high"], help="Reasoning effort")

    # Command: init
    init_parser = subparsers.add_parser("init", help="Initialize sample configuration and sample task")
    init_parser.add_argument("--dir", default=".", help="Target directory for initialization")

    return parser


def handle_init(args: argparse.Namespace) -> int:
    target_dir = Path(args.dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. harness.yaml
    config_file = target_dir / "harness.yaml"
    if not config_file.exists():
        HarnessConfig().to_yaml(config_file)
        console.print(f"[green]✔[/green] Created configuration: [bold]{config_file}[/bold]")
    else:
        console.print(f"[yellow]![/yellow] Configuration already exists: [bold]{config_file}[/bold]")

    # 2. sample_tasks.json
    tasks_file = target_dir / "sample_tasks.json"
    if not tasks_file.exists():
        sample_task = TaskSpec(
            task_id="sample_math_fix",
            description="Fix the subtract bug in math_ops.py so that sub(a, b) returns a - b instead of a + b.",
            test_command="python3 -c 'import math_ops; assert math_ops.sub(10, 3) == 7'",
        )
        TaskDataset([sample_task]).save(tasks_file)
        console.print(f"[green]✔[/green] Created sample tasks file: [bold]{tasks_file}[/bold]")

    console.print(Panel(
        "[bold green]Antigravity Harness initialized successfully![/bold green]\n\n"
        "To run a benchmark:\n"
        "  agy-harness benchmark --dataset sample_tasks.json\n\n"
        "To run a single task:\n"
        "  agy-harness run --task sample_tasks.json",
        title="Ready",
        expand=False,
    ))
    return 0


async def handle_run(args: argparse.Namespace) -> int:
    config = HarnessConfig.from_yaml(args.config) if args.config else HarnessConfig()

    if args.model:
        config.runner.model = args.model
    if args.effort:
        config.runner.effort = args.effort
    if args.timeout:
        config.runner.timeout_seconds = args.timeout
    if args.keep_workspace:
        config.cleanup_worktree = False

    task_path = Path(args.task).resolve()
    dataset = TaskDataset.load(task_path)
    if not dataset.tasks:
        console.print(f"[red]Error: No tasks found in {task_path}[/red]")
        return 1

    task = dataset.tasks[0]
    engine = HarnessEngine(config=config)

    console.print(f"[bold blue]Running Task:[/bold blue] {task.task_id}")
    exec_res, eval_res, telem = await engine.run_task(task)

    status_color = "green" if eval_res.status == EvalStatus.PASS else "red"
    console.print(Panel(
        f"[bold]Task ID:[/bold] {eval_res.task_id}\n"
        f"[bold]Status:[/bold] [{status_color}]{eval_res.status.value}[/{status_color}]\n"
        f"[bold]Duration:[/bold] {eval_res.duration_seconds:.2f}s\n"
        f"[bold]Turns:[/bold] {telem.total_turns}\n"
        f"[bold]Tool Calls:[/bold] {telem.total_tool_calls}\n"
        f"[bold]Message:[/bold] {eval_res.message}",
        title="Task Result",
        expand=False,
    ))

    return 0 if eval_res.status == EvalStatus.PASS else 1


async def handle_benchmark(args: argparse.Namespace) -> int:
    config = HarnessConfig.from_yaml(args.config) if args.config else HarnessConfig()

    if args.model:
        config.runner.model = args.model
    if args.effort:
        config.runner.effort = args.effort

    dataset_path = Path(args.dataset).resolve()
    dataset = TaskDataset.load(dataset_path)

    engine = HarnessEngine(config=config)
    report = await engine.run_benchmark(dataset=dataset, output_dir=args.output)

    # Render summary table
    table = Table(title="Benchmark Execution Summary", show_header=True, header_style="bold magenta")
    table.add_column("Task ID", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Duration", justify="right")
    table.add_column("Passed Tests", justify="right")
    table.add_column("Failed Tests", justify="right")

    for r in report.eval_results:
        status_style = "[green]PASS[/green]" if r.status == EvalStatus.PASS else f"[red]{r.status.value}[/red]"
        table.add_row(
            r.task_id,
            status_style,
            f"{r.duration_seconds:.1f}s",
            str(len(r.tests_passed)),
            str(len(r.tests_failed)),
        )

    console.print(table)
    console.print(f"\n[bold]Overall Pass Rate:[/bold] {report.pass_rate:.1f}% ({report.passed_tasks}/{report.total_tasks} passed)\n")
    return 0 if report.passed_tasks == report.total_tasks else 1


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "init":
        sys.exit(handle_init(args))
    elif args.command == "run":
        sys.exit(asyncio.run(handle_run(args)))
    elif args.command == "benchmark":
        sys.exit(asyncio.run(handle_benchmark(args)))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
