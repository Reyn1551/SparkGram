"""
OpenCode CLI Adapter for SparkGram.
Constructs commands, executes subprocesses, and parses stream events safely.
"""
import re
import os
import json
import logging
import asyncio
from typing import List, Optional, Dict, Any, Callable, AsyncGenerator

from ..config import settings
from ..engine.runner import SubprocessRunner
from ..core.models import ExecutionResult

log = logging.getLogger(__name__)

# Regex to strip ANSI escape sequences
ANSI_ESCAPE_REGEX = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def clean_ansi(text: str) -> str:
    """Removes terminal color and cursor escape sequences."""
    return ANSI_ESCAPE_REGEX.sub("", text)


class OpenCodeAdapter:
    """Interface to OpenCode CLI runner."""

    @staticmethod
    def build_run_command(
        prompt: str,
        work_dir: str,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
        auto_approve: bool = True,
        format_mode: str = "default"
    ) -> List[str]:
        """Constructs opencode run arguments."""
        cmd = ["opencode", "run", prompt, "--dir", work_dir, "--format", format_mode]
        chosen_model = model or settings.runtime_model or settings.model
        if chosen_model:
            cmd.extend(["--model", chosen_model])
        if session_id:
            cmd.extend(["--session", session_id])
        if auto_approve:
            cmd.append("--auto")
        return cmd

    @classmethod
    async def run_prompt_streaming(
        cls,
        prompt: str,
        work_dir: str,
        model: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout_sec: float = 600.0,
        on_chunk: Optional[Callable[[str], Any]] = None,
        on_proc_started: Optional[Callable[[asyncio.subprocess.Process], Any]] = None,
    ) -> ExecutionResult:
        """Executes opencode prompt and feeds output chunks via callback."""
        cmd = cls.build_run_command(
            prompt=prompt,
            work_dir=work_dir,
            model=model,
            session_id=session_id,
            auto_approve=True,
            format_mode="default"
        )
        
        async def line_handler(raw_line: str):
            clean_line = clean_ansi(raw_line)
            if on_chunk:
                if asyncio.iscoroutinefunction(on_chunk):
                    await on_chunk(clean_line)
                else:
                    on_chunk(clean_line)

        result = await SubprocessRunner.run_command(
            cmd=cmd,
            cwd=work_dir,
            timeout_sec=timeout_sec,
            on_line=line_handler,
            on_proc_started=on_proc_started,
        )
        # Clean final output
        result.output = clean_ansi(result.output)
        if result.error:
            result.error = clean_ansi(result.error)
        return result
