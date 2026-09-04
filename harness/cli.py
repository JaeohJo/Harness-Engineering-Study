"""Antigravity 하네스 엔지니어링 CLI 인터페이스 모듈.

터미널에서 run, benchmark, init 하위 명령어를 통해 손쉽게 단일 태스크 검증,
벤치마크 일괄 채점 및 환경 초기화를 실행할 수 있는 콘솔 인터페이스를 제공합니다.
"""

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
    """커맨드라인 옵션 파서를 구성합니다."""
    parser = argparse.ArgumentParser(
        prog="agy-harness",
        description="Antigravity CLI 대상 프로덕션 레벨 하네스 엔지니어링 프레임워크",
    )
    subparsers = parser.add_subparsers(dest="command", help="사용 가능한 하위 명령어")

    # 1. 단일 태스크 실행 명령어: run
    run_parser = subparsers.add_parser("run", help="단일 태스크를 하네스 파이프라인으로 실행 및 검증")
    run_parser.add_argument("--task", "-t", required=True, help="태스크 JSON 파일 경로")
    run_parser.add_argument("--config", "-c", help="harness.yaml 설정 파일 경로")
    run_parser.add_argument("--model", "-m", help="적용할 LLM 모델명 재정의")
    run_parser.add_argument("--effort", choices=["low", "medium", "high"], help="모델 추론 노력 수준 (low|medium|high)")
    run_parser.add_argument("--timeout", type=float, help="실행 제한 시간(초)")
    run_parser.add_argument("--keep-workspace", action="store_true", help="실행 후 격리 워크스페이스 보존 (디버깅용)")

    # 2. 벤치마크 일괄 실행 명령어: benchmark
    bench_parser = subparsers.add_parser("benchmark", help="데이터셋 전체에 대해 벤치마크 평가 일괄 실행")
    bench_parser.add_argument("--dataset", "-d", required=True, help="데이터셋 JSON 또는 JSONL 파일 경로")
    bench_parser.add_argument("--output", "-o", default="reports", help="결과 보고서 저장 대상 폴더")
    bench_parser.add_argument("--config", "-c", help="harness.yaml 설정 파일 경로")
    bench_parser.add_argument("--model", "-m", help="적용할 LLM 모델명 재정의")
    bench_parser.add_argument("--effort", choices=["low", "medium", "high"], help="모델 추론 노력 수준")

    # 3. 프로젝트 초기화 명령어: init
    init_parser = subparsers.add_parser("init", help="기본 harness.yaml 설정 및 샘플 태스크 파일 생성")
    init_parser.add_argument("--dir", default=".", help="초기화 파일들을 생성할 디렉터리 경로")

    return parser


def handle_init(args: argparse.Namespace) -> int:
    """init 하위 명령어 처리 핸들러: 기본 설정과 샘플 태스크를 생성합니다."""
    target_dir = Path(args.dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. harness.yaml 생성
    config_file = target_dir / "harness.yaml"
    if not config_file.exists():
        HarnessConfig().to_yaml(config_file)
        console.print(f"[green]✔[/green] 기본 설정 파일 생성 완료: [bold]{config_file}[/bold]")
    else:
        console.print(f"[yellow]![/yellow] 이미 설정 파일이 존재합니다: [bold]{config_file}[/bold]")

    # 2. sample_tasks.json 생성
    tasks_file = target_dir / "sample_tasks.json"
    if not tasks_file.exists():
        sample_task = TaskSpec(
            task_id="sample_math_fix",
            description="math_ops.py 파일의 뺄셈 버그를 수정하여 sub(a, b)가 a + b 대신 a - b를 반환하도록 하십시오.",
            initial_files={
                "math_ops.py": "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a + b  # 버그: 뺄셈 대신 덧셈이 구현되어 있음\n"
            },
            test_command="python3 -c 'import math_ops; assert math_ops.sub(10, 3) == 7'",
        )
        TaskDataset([sample_task]).save(tasks_file)
        console.print(f"[green]✔[/green] 샘플 태스크 데이터셋 생성 완료: [bold]{tasks_file}[/bold]")

    console.print(Panel(
        "[bold green]Antigravity 하네스 환경이 성공적으로 초기화되었습니다![/bold green]\n\n"
        "벤치마크 실행:\n"
        "  agy-harness benchmark --dataset sample_tasks.json\n\n"
        "단일 태스크 실행:\n"
        "  agy-harness run --task sample_tasks.json",
        title="초기화 완료",
        expand=False,
    ))
    return 0


async def handle_run(args: argparse.Namespace) -> int:
    """run 하위 명령어 처리 핸들러: 단일 태스크를 실행하고 결과를 요약 출력합니다."""
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
        console.print(f"[red]오류: {task_path} 파일에서 태스크를 찾을 수 없습니다.[/red]")
        return 1

    task = dataset.tasks[0]
    engine = HarnessEngine(config=config)

    console.print(f"[bold blue]태스크 실행 중:[/bold blue] {task.task_id}")
    exec_res, eval_res, telem = await engine.run_task(task)

    status_color = "green" if eval_res.status == EvalStatus.PASS else "red"
    console.print(Panel(
        f"[bold]태스크 ID:[/bold] {eval_res.task_id}\n"
        f"[bold]최종 상태:[/bold] [{status_color}]{eval_res.status.value}[/{status_color}]\n"
        f"[bold]소요 시간:[/bold] {eval_res.duration_seconds:.2f}초\n"
        f"[bold]대화 턴 수:[/bold] {telem.total_turns}회\n"
        f"[bold]도구 호출 수:[/bold] {telem.total_tool_calls}회\n"
        f"[bold]메시지:[/bold] {eval_res.message}",
        title="태스크 실행 결과",
        expand=False,
    ))

    return 0 if eval_res.status == EvalStatus.PASS else 1


async def handle_benchmark(args: argparse.Namespace) -> int:
    """benchmark 하위 명령어 처리 핸들러: 전체 데이터셋을 평가하고 리포트를 생성합니다."""
    config = HarnessConfig.from_yaml(args.config) if args.config else HarnessConfig()

    if args.model:
        config.runner.model = args.model
    if args.effort:
        config.runner.effort = args.effort

    dataset_path = Path(args.dataset).resolve()
    dataset = TaskDataset.load(dataset_path)

    engine = HarnessEngine(config=config)
    report = await engine.run_benchmark(dataset=dataset, output_dir=args.output)

    # 터미널 요약 테이블 렌더링
    table = Table(title="벤치마크 평가 종합 결과", show_header=True, header_style="bold magenta")
    table.add_column("태스크 ID", style="cyan")
    table.add_column("판정 상태", justify="center")
    table.add_column("소요 시간", justify="right")
    table.add_column("통과 테스트", justify="right")
    table.add_column("실패 테스트", justify="right")

    for r in report.eval_results:
        status_style = "[green]PASS[/green]" if r.status == EvalStatus.PASS else f"[red]{r.status.value}[/red]"
        table.add_row(
            r.task_id,
            status_style,
            f"{r.duration_seconds:.1f}초",
            f"{len(r.tests_passed)}건",
            f"{len(r.tests_failed)}건",
        )

    console.print(table)
    console.print(f"\n[bold]전체 해결률(Pass Rate):[/bold] {report.pass_rate:.1f}% ({report.passed_tasks}/{report.total_tasks}건 통과)\n")
    return 0 if report.passed_tasks == report.total_tasks else 1


def main() -> None:
    """CLI 메인 진입점 함수."""
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
