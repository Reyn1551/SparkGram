"""
Concurrent Non-Blocking Dual-Stream Reader for SparkGram.
Prevents OS pipe buffer deadlocks by consuming stdout and stderr concurrently with a 10MB limit.
"""
import asyncio
import logging
from typing import AsyncGenerator, Tuple, List, Optional

log = logging.getLogger(__name__)


class ConcurrentStreamReader:
    """Reads stdout and stderr concurrently without OS pipe saturation deadlocks."""

    def __init__(self, proc: asyncio.subprocess.Process, max_buffer_bytes: int = 10 * 1024 * 1024):
        self.proc = proc
        self.max_buffer_bytes = max_buffer_bytes
        self.stderr_lines: List[str] = []
        self._stderr_task: Optional[asyncio.Task] = None

    async def _consume_stderr(self) -> None:
        """Continuously drains stderr in the background to prevent OS pipe blocking."""
        if not self.proc.stderr:
            return
        try:
            while True:
                line = await self.proc.stderr.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded:
                    self.stderr_lines.append(decoded)
                    # Keep bounded in memory (last 200 lines)
                    if len(self.stderr_lines) > 200:
                        self.stderr_lines.pop(0)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.debug(f"Stderr drain exception: {e}")

    async def read_stdout_lines(self) -> AsyncGenerator[str, None]:
        """Asynchronously streams lines from stdout while draining stderr in parallel."""
        self._stderr_task = asyncio.create_task(self._consume_stderr())
        
        buffer = bytearray()
        if not self.proc.stdout:
            return

        try:
            while True:
                # Read chunks up to 64KB
                chunk = await self.proc.stdout.read(65536)
                if not chunk:
                    break
                
                buffer.extend(chunk)
                if len(buffer) > self.max_buffer_bytes:
                    log.warning("Stream buffer exceeded 10MB limit; truncating oldest bytes.")
                    buffer = buffer[-self.max_buffer_bytes:]

                # Split on newlines
                while b"\n" in buffer:
                    idx = buffer.index(b"\n")
                    line_bytes = buffer[:idx]
                    buffer = buffer[idx + 1:]
                    line_str = line_bytes.decode("utf-8", errors="replace").strip()
                    if line_str:
                        yield line_str

            # Flush remaining buffer if any
            if buffer:
                remaining = buffer.decode("utf-8", errors="replace").strip()
                if remaining:
                    yield remaining

        finally:
            if self._stderr_task and not self._stderr_task.done():
                try:
                    await asyncio.wait_for(self._stderr_task, timeout=1.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    self._stderr_task.cancel()

    def get_stderr_output(self) -> str:
        """Returns collected stderr logs."""
        return "\n".join(self.stderr_lines)
