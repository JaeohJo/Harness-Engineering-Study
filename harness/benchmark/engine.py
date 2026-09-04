"""Antigravity CLI 엔드투엔드 벤치마크 오케스트레이션 엔진 모듈.

태스크 환경 프로비저닝(Git Worktree/Temp), 보안 가드레일 주입, agy CLI 비동기 실행,
Diff 추출, 정답 평가, 세션 텔레메트리 수집 및 결과 리포트 생성을 하나로 결합합니다.
"""

from __future__ import annotations

import subprocess
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
    """하네스 실행 수명주기 전반을 조율하는 최상위 오케스트레이터 클래스."""

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
        """태스크 사양에 따라 Git Worktree 또는 로컬 임시 샌드박스 환경을 인스턴스화합니다."""
        repo_path = Path(task.repo_path).resolve() if task.repo_path else None

        # 유효한 Git 저장소인 경우 완전 격리된 Git Worktree 생성
        if repo_path and (repo_path / ".git").exists():
            return GitWorktreeEnvironment(
                repo_path=repo_path,
                base_commit=task.base_commit or "HEAD",
                task_id=task.task_id,
                auto_cleanup=self.config.cleanup_worktree,
            )
        else:
            # 일반 디렉터리 또는 소스 미지정 시 임시 샌드박스 폴더 생성
            return LocalTempEnvironment(
                source_dir=repo_path,
                task_id=task.task_id,
                auto_cleanup=self.config.cleanup_worktree,
            )

    async def run_task(
        self,
        task: TaskSpec,
    ) -> tuple[ExecutionResult, EvalResult, TelemetryData]:
        """단일 태스크에 대해 프로비저닝부터 에이전트 구동, 평가, 텔레메트리 수집까지 전 과정을 실행합니다."""
        logger.info(f"태스크 실행 시작: [bold cyan]{task.task_id}[/bold cyan]")
        start_time = time.time()

        # 1. 격리된 작업 환경 프로비저닝
        env = self._create_environment(task)
        workspace_path = env.setup()

        try:
            # 1-1. 사전 초기 파일(initial_files) 생성
            if task.initial_files:
                for rel_path, file_content in task.initial_files.items():
                    target_file = workspace_path / rel_path
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    target_file.write_text(file_content, encoding="utf-8")

            # 1-2. 사전 준비 명령어(setup_command) 실행
            if task.setup_command:
                logger.debug(f"태스크 사전 설정 명령 실행: {task.setup_command}")
                subprocess.run(
                    task.setup_command,
                    shell=True,
                    cwd=str(workspace_path),
                    capture_output=True,
                    check=False,
                )

            # 1-3. 초기 파일 및 사전 설정 반영 후 측정 기준선(baseline) 재설정
            if task.initial_files or task.setup_command:
                env.reset_baseline()

            # 2. 보안 가드레일 및 hooks.json 자동 주입
            if self.config.enable_guardrails:
                self.hook_manager.inject_hooks(workspace_path)

            # 3. agy CLI 비대화형 에이전트 실행 (태스크 타임아웃 전달)
            exec_res = await self.runner.run(
                prompt=task.description,
                workspace_dir=str(workspace_path),
                task_id=task.task_id,
                timeout_seconds=task.timeout_seconds,
            )

            # 4. 에이전트가 수정한 Unified Diff 추출
            diff = env.get_diff()

            # 5. 코드 변경사항 정밀 평가 (구문 검증 및 테스트 통과 여부 채점)
            eval_res = self.evaluator.evaluate(
                workspace_dir=workspace_path,
                task=task,
                diff=diff,
            )

            # 6. 세션 트랜스크립트로부터 추론 토큰 및 도구 사용 텔레메트리 추출
            telemetry = self.transcript_parser.extract_telemetry(
                task_id=task.task_id,
                conversation_id=exec_res.conversation_id,
                duration_seconds=time.time() - start_time,
            )
            telemetry.files_modified = env.get_modified_files()

            # Diff 분석 결과로부터 추가/삭제 라인 수 집계 연계
            if "diff_analysis" in eval_res.details:
                diff_meta = eval_res.details["diff_analysis"]
                telemetry.lines_added = diff_meta.get("lines_added", 0)
                telemetry.lines_removed = diff_meta.get("lines_removed", 0)

            logger.info(
                f"태스크 완료 [bold cyan]{task.task_id}[/bold cyan]: "
                f"상태=[bold {'green' if eval_res.status == EvalStatus.PASS else 'red'}]{eval_res.status.value}[/] "
                f"({eval_res.duration_seconds:.1f}초 소요)"
            )

            return exec_res, eval_res, telemetry

        finally:
            # 7. 워크스페이스 정리 (설정에 따라 자동 삭제)
            if self.config.cleanup_worktree:
                env.cleanup()

    async def run_benchmark(
        self,
        dataset: TaskDataset,
        output_dir: Optional[Path | str] = None,
    ) -> BenchmarkReport:
        """데이터셋에 포함된 모든 태스크를 순차 실행하고 종합 벤치마크 보고서를 작성합니다."""
        out_dir = Path(output_dir or self.config.output_dir)
        exec_results: List[ExecutionResult] = []
        eval_results: List[EvalResult] = []
        telemetries: List[TelemetryData] = []

        logger.info(f"총 [bold yellow]{len(dataset)}[/bold yellow]개 태스크 벤치마크 평가 시작...")

        for task in dataset:
            try:
                exec_res, eval_res, telem = await self.run_task(task)
                exec_results.append(exec_res)
                eval_results.append(eval_res)
                telemetries.append(telem)
            except Exception as e:
                logger.error(f"태스크 '{task.task_id}' 실행 중 예기치 않은 오류: {e}")
                eval_results.append(
                    EvalResult(
                        task_id=task.task_id,
                        status=EvalStatus.ERROR,
                        message=f"하네스 런타임 오류: {e}",
                    )
                )

        # 종합 리포트 생성 및 저장
        report = BenchmarkReport(
            eval_results=eval_results,
            exec_results=exec_results,
            telemetry_data=telemetries,
            model_name=self.config.runner.model or "default_model",
        )

        json_path, md_path = report.save(out_dir)
        logger.info(f"벤치마크 완료! 보고서가 저장되었습니다:\n- {md_path}\n- {json_path}")

        return report
