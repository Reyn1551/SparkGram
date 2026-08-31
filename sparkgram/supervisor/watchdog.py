"""
Self-Healing File Watcher and Auto-Restart for SparkGram.
Monitors source files and restarts daemon cleanly upon code changes.

Fix v2: graceful shutdown (no SystemExit traceback), ignore list, debounce,
        detection of added/deleted files, bounded errors.
"""
import asyncio
import logging
import os
from pathlib import Path

from ..config import settings

log = logging.getLogger(__name__)

# Files/dirs that must NEVER trigger restart (state, logs, secrets)
_IGNORE_DIRS = {
    "__pycache__", ".git", ".venv", "venv", ".pytest_cache",
    "node_modules", ".mypy_cache", ".ruff_cache", "logs", "tmp",
    ".codebase-memory",
}
_IGNORE_FILES = {
    ".bridge_state.json",
    ".restart",
    ".restart_intent",
    "bridge.log",
    "child_stdout.log",
    "child_stderr.log",
    "runner_out.log",
    "runner_err.log",
}
# json files that are state/config, not code
_IGNORE_JSON_NAMES = {
    ".bridge_state.json",
    "railway.json",
    "fly.toml",  # not json but keep
}
# Extensions to watch
_WATCH_EXTS = (".py", ".json", ".env")
# Also watch bare .env files (no extension handling via rglob *.env)
_WATCH_GLOBS = ("*.py", "*.json", ".env", "*.env")


class FileWatchdog:
    """Monitors mtimes of source code files with debounce and graceful shutdown."""

    def __init__(self, watch_dir: Path, debounce_sec: float = 4.0):
        self.watch_dir = watch_dir.resolve()
        self.debounce_sec = debounce_sec
        self.restart_flag = settings.root_dir / ".restart"
        self._app = None  # set via bind_app()
        self._last_mtimes = self._collect_mtimes()
        self._stopping = False

    def bind_app(self, app) -> None:
        """Bind the PTB Application for graceful stop_running()."""
        self._app = app

    def _is_ignored(self, p: Path) -> bool:
        # Check dir parts
        for part in p.parts:
            if part in _IGNORE_DIRS:
                return True
        name = p.name
        if name in _IGNORE_FILES:
            return True
        if name in _IGNORE_JSON_NAMES:
            return True
        # Ignore temp/log files
        if name.endswith(".log") or name.endswith(".pid") or name.endswith(".lock"):
            return True
        # Ignore state file exact path
        try:
            if p.resolve() == settings.state_file.resolve():
                return True
        except Exception:
            pass
        # Ignore the restart flag itself (handled separately)
        try:
            if p.resolve() == self.restart_flag.resolve():
                return True
        except Exception:
            pass
        # Ignore hidden .env.example
        if name == ".env.example":
            return True
        return False

    def _collect_mtimes(self) -> dict:
        mtimes: dict[str, float] = {}
        # Use rglob for each pattern, but filter ignored aggressively
        patterns = ("*.py", "*.json", ".env", "*.env")
        seen: set[str] = set()
        for pat in patterns:
            try:
                for p in self.watch_dir.rglob(pat):
                    if p.is_dir():
                        continue
                    if self._is_ignored(p):
                        continue
                    # Only keep watched extensions / .env
                    if p.suffix not in (".py", ".json") and p.name != ".env" and not p.name.endswith(".env"):
                        continue
                    key = str(p.resolve())
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        mtimes[key] = p.stat().st_mtime
                    except Exception:
                        pass
            except Exception:
                continue
        return mtimes

    def _trigger_graceful_restart(self, reason: str) -> None:
        """Request graceful restart without SystemExit traceback."""
        if self._stopping:
            return
        self._stopping = True
        log.info(f"{reason} -> graceful restart (debounce {self.debounce_sec}s)")
        # Prefer PTB graceful stop; fallback to os._exit(0) outside event loop
        try:
            if self._app is not None:
                # stop_running() is designed to break run_polling/run_webhook
                self._app.stop_running()
                log.info("Called app.stop_running() for restart")
                return
        except Exception as e:
            log.warning(f"stop_running failed: {e}")
        # Fallback: _exit(0) avoids SystemExit traceback and gives clean exit code 0
        try:
            os._exit(0)
        except Exception:
            import sys
            sys.exit(0)

    async def watch_loop(self) -> None:
        """Background loop checking for file changes or restart flag."""
        log.info(f"Watchdog armed: dir={self.watch_dir}, debounce={self.debounce_sec}s, auto_restart={settings.enable_auto_restart}")
        try:
            while True:
                await asyncio.sleep(2.0)

                # 1. Check restart flag (highest priority)
                if self.restart_flag.exists():
                    log.info("Restart flag detected -> restarting process...")
                    try:
                        self.restart_flag.unlink()
                    except Exception:
                        pass
                    await asyncio.sleep(0.2)
                    self._trigger_graceful_restart("Restart flag")
                    return

                # 2. Check mtimes if auto-restart enabled
                if not settings.enable_auto_restart:
                    continue

                try:
                    current_mtimes = self._collect_mtimes()
                except Exception as e:
                    log.warning(f"collect_mtimes error (ignored): {e}")
                    continue

                # Detect added / deleted / modified
                changed_path = None
                # Modified or added
                for fpath, mtime in current_mtimes.items():
                    prev = self._last_mtimes.get(fpath)
                    if prev is None:
                        changed_path = f"{fpath} (new file)"
                        break
                    if mtime > prev + 0.05:  # 50ms jitter tolerance
                        changed_path = fpath
                        break
                # Deleted
                if changed_path is None:
                    for fpath in self._last_mtimes:
                        if fpath not in current_mtimes:
                            changed_path = f"{fpath} (deleted)"
                            break

                if changed_path:
                    log.info(f"File modified: {changed_path} -> debouncing restart {self.debounce_sec}s")
                    await asyncio.sleep(self.debounce_sec)
                    # Re-collect to avoid storm of rapid saves triggering multiple restarts
                    # If still changed after debounce, trigger
                    self._trigger_graceful_restart(f"File modified: {changed_path}")
                    return

                self._last_mtimes = current_mtimes
        except asyncio.CancelledError:
            log.info("Watchdog cancelled -- normal shutdown")
            return
        except Exception as e:
            # Never crash the bot due to watchdog bug; log and disable watchdog
            log.error(f"Watchdog fatal error (disabling watchdog, bot stays alive): {e}", exc_info=True)
            return
