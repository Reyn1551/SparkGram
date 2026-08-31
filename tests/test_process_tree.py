"""
Unit Tests for Process Supervisor, Tree Killer, and Non-Blocking Stream Reader.
"""
import sys
import asyncio
import pytest
from sparkgram.engine.process_tree import ProcessTreeManager
from sparkgram.engine.stream_reader import ConcurrentStreamReader
from sparkgram.engine.runner import SubprocessRunner


@pytest.mark.asyncio
async def test_concurrent_stream_reader():
    # Run a python command that writes to both stdout and stderr
    script = (
        "import sys\n"
        "sys.stdout.write('line1\\nline2\\n')\n"
        "sys.stdout.flush()\n"
        "sys.stderr.write('err1\\nerr2\\n')\n"
        "sys.stderr.flush()\n"
    )
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    reader = ConcurrentStreamReader(proc)
    stdout_lines = []
    async for line in reader.read_stdout_lines():
        stdout_lines.append(line)

    await proc.wait()
    assert "line1" in stdout_lines
    assert "line2" in stdout_lines
    stderr_out = reader.get_stderr_output()
    assert "err1" in stderr_out


@pytest.mark.asyncio
async def test_subprocess_runner_timeout_and_kill():
    # Long sleeping script to test timeout
    script = "import time; time.sleep(10)"
    result = await SubprocessRunner.run_command(
        cmd=[sys.executable, "-c", script],
        timeout_sec=0.5
    )
    assert result.success is False
    assert "timed out" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_process_tree_manager_kill():
    ptm = ProcessTreeManager()
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(10)",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.returncode is None
    await ptm.kill_process_tree(proc, timeout=1.0)
    assert proc.returncode is not None
