"""Headless CLI runner for executing Antigravity CLI (agy) non-interactively."""

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
    """Subprocess runner for invoking the `agy` command-line interface in headless mode."""

    def __init__(self, config: Optional[RunnerConfig] = None):
        self.config = config or RunnerConfig()

    async def run(
        self,
        prompt: str,
        workspace_dir: str,
        task_id: str = "default_task",
        on_event: Optional[Callable[[StreamEvent], None]] = None,
        log_file: Optional[str] = None,
        **kwargs,
    ) -> ExecutionResult:
        """Executes agy CLI with the given prompt in the specified workspace directory asynchronously."""
        workspace_path = Path(workspace_dir).resolve()
        if not workspace_path.exists():
            raise FileNotFoundError(f"Workspace directory does not exist: {workspace_path}")

        cmd = self.config.build_cli_args(
            prompt=prompt,
            workspace_dir=str(workspace_path),
            log_file=log_file,
        )

        logger.debug(f"Starting agy runner command: {' '.join(cmd)}")
        start_time = time.time()

        events: List[StreamEvent] = []
        stdout_lines: List[str] = []
        stderr_chunks: List[str] = []
        final_response_parts: List[str] = []
        conversation_id: Optional[str] = None
        timed_out = False
        error_message: Optional[str] = None

        # Start the process in a new process group for clean signal dispatching
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(workspace_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=os.setsid if hasattr(os, "setsid") else None,
            )
        except FileNotFoundError as e:
            duration = time.time() - start_time
            return ExecutionResult(
                task_id=task_id,
                exit_code=-1,
                events=[],
                stdout="",
                stderr="",
                duration_seconds=duration,
                timed_out=False,
                error_message=f"Antigravity CLI binary not found at '{self.config.agy_bin_path}': {e}",
            )

        async def read_stdout():
            nonlocal conversation_id
            assert process.stdout is not None
            while True:
                line_bytes = await process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace")
                stdout_lines.append(line)

                event = StreamEvent.from_ndjson(line)
                if event:
                    events.append(event)
                    if event.type in (StreamEventType.DELTA, StreamEventType.DONE):
                        if event.content:
                            final_response_parts.append(event.content)
                    if not conversation_id and event.raw_payload:
                        cid = event.raw_payload.get("conversation_id") or event.raw_payload.get("conversationId")
                        if cid:
                            conversation_id = str(cid)

                    if on_event:
                        try:
                            on_event(event)
                        except Exception as cb_err:
                            logger.warning(f"Error in on_event callback: {cb_err}")

        async def read_stderr():
            assert process.stderr is not None
            while True:
                chunk_bytes = await process.stderr.readline()
                if not chunk_bytes:
                    break
                stderr_chunks.append(chunk_bytes.decode("utf-8", errors="replace"))

        timeout = self.config.timeout_seconds
        try:
            await asyncio.wait_for(
                asyncio.gather(read_stdout(), read_stderr(), process.wait()),
                timeout=timeout,
            )
            exit_code = process.returncode if process.returncode is not None else 0
        except asyncio.TimeoutError:
            timed_out = True
            error_message = f"Execution timed out after {timeout} seconds"
            logger.warning(f"Task '{task_id}' timed out. Terminating process group...")
            await self._terminate_process(process)
            exit_code = -1
        except Exception as e:
            error_message = f"Process execution failed: {e}"
            logger.error(f"Task '{task_id}' encountered unexpected error: {e}")
            await self._terminate_process(process)
            exit_code = -1

        duration = time.time() - start_time
        stdout_text = "".join(stdout_lines)
        stderr_text = "".join(stderr_chunks)

        # Fallback for final_response if not captured via stream events
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
        """Gracefully terminates a subprocess, falling back to SIGKILL if necessary."""
        if process.returncode is not None:
            return

        pid = process.pid
        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            else:
                process.terminate()
        except (ProcessLookupError, PermissionError):
            return

        # Wait briefly for graceful shutdown
        for _ in range(15):
            await asyncio.sleep(0.2)
            if process.returncode is not None:
                return

        # Force kill if still running
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
        """Synchronously executes the agent runner."""
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
