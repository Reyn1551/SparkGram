"""
Subprocess Execution Runner for SparkGram.
Orchestrates process spawning, live stream consumption, and cancellation.
"""
import os
import sys
import time
import asyncio
import logging
from typing import List, Optional, AsyncGenerator, Dict, Any, Callable

from .process_tree import process_supervisor
from .stream_reader import ConcurrentStreamReader
from ..core.models import ExecutionResult

log = logging.getLogger(__name__)


class SubprocessRunner:
    """Manages spawning and streaming lifecycle of CLI subprocesses."""

    @staticmethod
    async def run_command(
        cmd: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout_sec: Optional[float] = 300.0,
        on_line: Optional[Callable[[str], Any]] = None,
        on_proc_started: Optional[Callable[[asyncio.subprocess.Process], Any]] = None,
    ) -> ExecutionResult:
        """Executes a command with non-blocking stream reading and timeout protection."""
        start_time = time.monotonic()
        proc: Optional[asyncio.subprocess.Process] = None
        output_lines: List[str] = []

        try:
            # Platform specific subprocess flags
            kwargs: Dict[str, Any] = {
                "stdin": asyncio.subprocess.DEVNULL,
                "stdout": asyncio.subprocess.PIPE,
                "stderr": asyncio.subprocess.PIPE,
                "cwd": cwd,
                "env": env,
            }
            if sys.platform != "win32":
                kwargs["preexec_fn"] = os.setsid  # POSIX: new process group for killpg

            proc = await asyncio.create_subprocess_exec(*cmd, **kwargs)
            if proc.pid:
                process_supervisor.assign_process(proc.pid)

            if on_proc_started and proc:
                try:
                    if asyncio.iscoroutinefunction(on_proc_started):
                        await on_proc_started(proc)
                    else:
                        on_proc_started(proc)
                except Exception as e:
                    log.debug(f"on_proc_started callback error: {e}")

            reader = ConcurrentStreamReader(proc)

            async def stream_worker():
                async for line in reader.read_stdout_lines():
                    output_lines.append(line)
                    if on_line:
                        try:
                            if asyncio.iscoroutinefunction(on_line):
                                await on_line(line)
                            else:
                                on_line(line)
                        except Exception as e:
                            log.debug(f"on_line callback error: {e}")

            if timeout_sec:
                await asyncio.wait_for(stream_worker(), timeout=timeout_sec)
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            else:
                await stream_worker()
                await proc.wait()

            duration = time.monotonic() - start_time
            full_stdout = "\n".join(output_lines)
            stderr_out = reader.get_stderr_output()

            return ExecutionResult(
                success=(proc.returncode == 0),
                output=full_stdout,
                error=stderr_out if proc.returncode != 0 else None,
                return_code=proc.returncode or 0,
                duration_sec=duration,
            )

        except asyncio.TimeoutError:
            duration = time.monotonic() - start_time
            if proc:
                await process_supervisor.kill_process_tree(proc)
            return ExecutionResult(
                success=False,
                output="\n".join(output_lines),
                error=f"Command timed out after {timeout_sec}s.",
                return_code=-1,
                duration_sec=duration,
            )

        except asyncio.CancelledError:
            duration = time.monotonic() - start_time
            if proc:
                await process_supervisor.kill_process_tree(proc)
            raise

        except Exception as e:
            duration = time.monotonic() - start_time
            if proc:
                await process_supervisor.kill_process_tree(proc)
            return ExecutionResult(
                success=False,
                output="\n".join(output_lines),
                error=str(e),
                return_code=-1,
                duration_sec=duration,
            )
