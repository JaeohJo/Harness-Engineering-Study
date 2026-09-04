"""Antigravity CLI (agy) 헤드리스 비동기 실행기 모듈.

agy 바이너리를 비대화형(Headless) 서브프로세스로 실행하며, 표준 출력으로 전달되는
NDJSON 스트림을 실시간 파싱하여 이벤트 콜백 호출, 타임아웃 감시 및 프로세스 생명주기를 제어합니다.
"""

from __future__ import annotations

import asyncio
import os
import signal
import time
from pathlib import Path
from typing import Callable, List, Optional

from harness.core.config import RunnerConfig
from harness.core.logging import logger
from harness.core.models import (
    ExecutionResult,
    StreamEvent,
    StreamEventType,
)
from harness.runner.base import BaseRunner


class CliRunner(BaseRunner):
    """Antigravity CLI(agy)를 비대화형 서브프로세스로 구동하는 실행기."""

    def __init__(self, config: Optional[RunnerConfig] = None):
        self.config = config or RunnerConfig()

    async def run(
        self,
        prompt: str,
        workspace_dir: str,
        task_id: str = "default_task",
        on_event: Optional[Callable[[StreamEvent], None]] = None,
        log_file: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        **kwargs,
    ) -> ExecutionResult:
        """지정된 워크스페이스에서 agy CLI를 실행하고 결과를 수집합니다.

        주요 로직:
        1. 워크스페이스 유효성 검증 및 CLI 실행 인자 목록 빌드
        2. 독립된 프로세스 그룹(os.setsid)으로 서브프로세스 생성 (클린 종료 보장)
        3. stdout 스트림을 라인 단위로 읽어 NDJSON을 실시간 역직렬화
        4. stderr 스트림 병렬 수집
        5. 타임아웃 감시: 초과 시 SIGTERM -> SIGKILL 순차적 강제 종료
        6. 대화 세션 ID 및 최종 응답 텍스트 추출 후 ExecutionResult 반환
        """
        workspace_path = Path(workspace_dir).resolve()
        if not workspace_path.exists():
            raise FileNotFoundError(f"워크스페이스 디렉터리가 존재하지 않습니다: {workspace_path}")

        # CLI 커맨드 인자 리스트 생성 (태스크 타임아웃 전달)
        effective_timeout = timeout_seconds if timeout_seconds is not None else self.config.timeout_seconds
        cmd = self.config.build_cli_args(
            prompt=prompt,
            workspace_dir=str(workspace_path),
            log_file=log_file,
            timeout_seconds=effective_timeout,
        )

        logger.debug(f"agy 실행 명령어: {' '.join(cmd)}")
        start_time = time.time()

        events: List[StreamEvent] = []
        stdout_lines: List[str] = []
        stderr_chunks: List[str] = []
        final_response_parts: List[str] = []
        conversation_id: Optional[str] = None
        timed_out = False
        error_message: Optional[str] = None

        # 프로세스 그룹 분리를 위해 os.setsid 지정 (타임아웃 시 자식 프로세스 전체 안전 종료)
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(workspace_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )
        except FileNotFoundError as e:
            # agy 바이너리를 찾을 수 없는 경우
            duration = time.time() - start_time
            return ExecutionResult(
                task_id=task_id,
                exit_code=-1,
                events=[],
                stdout="",
                stderr="",
                duration_seconds=duration,
                timed_out=False,
                error_message=f"Antigravity CLI 바이너리를 찾을 수 없습니다 ('{self.config.agy_bin_path}'): {e}",
            )

        async def read_stdout():
            """stdout 스트림을 실시간으로 읽고 NDJSON 이벤트를 파싱합니다."""
            nonlocal conversation_id
            assert process.stdout is not None
            while True:
                line_bytes = await process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace")
                stdout_lines.append(line)

                # NDJSON 라인을 StreamEvent 객체로 변환
                event = StreamEvent.from_ndjson(line)
                if event:
                    events.append(event)
                    # 델타 응답 또는 완료 메시지인 경우 최종 응답 텍스트에 누적
                    if event.type in (StreamEventType.DELTA, StreamEventType.DONE):
                        if event.content:
                            final_response_parts.append(event.content)

                    # 세션 대화 ID가 아직 감지되지 않은 경우 페이로드에서 추출
                    if not conversation_id and event.raw_payload:
                        cid = event.raw_payload.get("conversation_id") or event.raw_payload.get("conversationId")
                        if cid:
                            conversation_id = str(cid)

                    # 사용자 등록 실시간 이벤트 콜백 실행
                    if on_event:
                        try:
                            on_event(event)
                        except Exception as cb_err:
                            logger.warning(f"on_event 콜백 실행 중 에러 발생: {cb_err}")

        async def read_stderr():
            """stderr 스트림을 병렬로 읽어 에러 로그를 보관합니다."""
            assert process.stderr is not None
            while True:
                chunk_bytes = await process.stderr.readline()
                if not chunk_bytes:
                    break
                stderr_chunks.append(chunk_bytes.decode("utf-8", errors="replace"))

        timeout = effective_timeout
        try:
            # 타임아웃 제한 내에서 입출력 스트림과 프로세스 종료 대기
            await asyncio.wait_for(
                asyncio.gather(read_stdout(), read_stderr(), process.wait()),
                timeout=timeout,
            )
            exit_code = process.returncode if process.returncode is not None else 0
        except asyncio.TimeoutError:
            timed_out = True
            error_message = f"에이전트 실행이 설정된 제한 시간({timeout}초)을 초과하여 중단되었습니다 (timed out)."
            logger.warning(f"태스크 '{task_id}' 타임아웃 발생. 프로세스 그룹 강제 종료 중...")
            await self._terminate_process(process)
            exit_code = -1
        except Exception as e:
            error_message = f"프로세스 실행 중 예외 발생: {e}"
            logger.error(f"태스크 '{task_id}' 오류 발생: {e}")
            await self._terminate_process(process)
            exit_code = -1

        duration = time.time() - start_time
        stdout_text = "".join(stdout_lines)
        stderr_text = "".join(stderr_chunks)

        # 스트림 이벤트에서 수집된 최종 텍스트가 없으면 stdout 텍스트를 폴백으로 사용
        final_response = "".join(final_response_parts).strip()
        if not final_response:
            final_response = stdout_text.strip()

        return ExecutionResult(
            task_id=task_id,
            conversation_id=conversation_id,
            exit_code=exit_code,
            events=events,
            stdout=stdout_text,
            stderr=stderr_text,
            duration_seconds=duration,
            timed_out=timed_out,
            error_message=error_message,
            final_response=final_response,
        )

    async def _terminate_process(self, process: asyncio.subprocess.Process) -> None:
        """서브프로세스 및 자식 프로세스 그룹을 단계적으로 안전하게 종료합니다."""
        if process.returncode is not None:
            return

        pid = process.pid
        # 1단계: SIGTERM 신호 전송 (정상 정리 기회 부여)
        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            else:
                process.terminate()
        except (ProcessLookupError, PermissionError):
            return

        # 최대 3초간 종료 대기
        for _ in range(15):
            await asyncio.sleep(0.2)
            if process.returncode is not None:
                return

        # 2단계: 여전히 생존 중인 경우 SIGKILL 강제 종료
        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            else:
                process.kill()
        except (ProcessLookupError, PermissionError):
            pass

    def run_sync(
        self,
        prompt: str,
        workspace_dir: str,
        task_id: str = "default_task",
        on_event: Optional[Callable[[StreamEvent], None]] = None,
        log_file: Optional[str] = None,
        **kwargs,
    ) -> ExecutionResult:
        """비동기 run 메서드를 블로킹 동기 방식으로 래핑하여 호출합니다."""
        return asyncio.run(
            self.run(
                prompt=prompt,
                workspace_dir=workspace_dir,
                task_id=task_id,
                on_event=on_event,
                log_file=log_file,
                **kwargs,
            )
        )
