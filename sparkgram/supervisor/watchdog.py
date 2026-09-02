"""
Self-Healing File Watcher and Auto-Restart for SparkGram.
Monitors source files and restarts daemon cleanly upon code changes.
Ensures zero-interruption: waits for active prompt tasks to complete before restarting.
"""
import asyncio
import logging
import os
from pathlib import Path

from ..config import settings

log = logging.getLogger(__name__)

# Files/dirs that must NEVER trigger restart (state, logs, secrets, runtime data)
_IGNORE_DIRS = {
    "__pycache__", ".git", ".venv", "venv", ".pytest_cache",
    "node_modules", ".mypy_cache", ".ruff_cache", "logs", "tmp",
    ".codebase-memory", "images", "exports", "memory", "scheduler",
    "riset", "tmp_images",
}
_IGNORE_FILES = {
    ".bridge_state.json",
    ".restart",
    ".restart_intent",
    "jobs.json",
    "bridge.log",
    "child_stdout.log",
    "child_stderr.log",
    "runner_out.log",
    "runner_err.log",
}
_IGNORE_JSON_NAMES = {
    ".bridge_state.json",
    "jobs.json",
    "railway.json",
    "fly.toml",
}
_WATCH_EXTS = (".py", ".json", ".env")
_WATCH_GLOBS = ("*.py", "*.json", ".env", "*.env")


class FileWatchdog:
    """Monitors mtimes of source code files with debounce, active task safety, and graceful shutdown."""

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
        if name.endswith(".log") or name.endswith(".pid") or name.endswith(".lock") or name.endswith(".tmp"):
            return True
        # Ignore state file exact path
        try:
            if p.resolve() == settings.state_file.resolve():
                return True
        except Exception as e:
            log.debug(f"Resolve state_file skip: {e}")
        # Ignore the restart flag itself
        try:
            if p.resolve() == self.restart_flag.resolve():
                return True
        except Exception as e:
            log.debug(f"Resolve restart_flag skip: {e}")
        if name == ".env.example":
            return True
        return False

    def _collect_mtimes(self) -> dict:
        mtimes: dict[str, float] = {}
        scan_dirs = []
        try:
            if self.watch_dir == settings.root_dir:
                scan_dirs = [settings.root_dir / "sparkgram"]
            else:
                scan_dirs = [self.watch_dir]
        except Exception:
            scan_dirs = [self.watch_dir]

        patterns = ("*.py", "*.json", ".env", "*.env")
        seen: set[str] = set()
        for base in scan_dirs:
            if not base.exists():
                continue
            for pat in patterns:
                try:
                    for p in base.rglob(pat):
                        if p.is_dir():
                            continue
                        if self._is_ignored(p):
                            continue
                        if p.suffix not in (".py", ".json") and p.name != ".env" and not p.name.endswith(".env"):
                            continue
                        key = str(p.resolve())
                        if key in seen:
                            continue
                        seen.add(key)
                        try:
                            mtimes[key] = p.stat().st_mtime
                        except Exception as e:
                            log.debug(f"Stat skip {key}: {e}")
                except Exception:
                    continue

        # Always include root .env / pyproject.toml mtime
        for extra in [settings.root_dir / ".env", settings.root_dir / "pyproject.toml"]:
            try:
                if extra.exists() and not self._is_ignored(extra):
                    key = str(extra.resolve())
                    if key not in seen:
                        mtimes[key] = extra.stat().st_mtime
            except Exception as e:
                log.debug(f"Extra mtime skip {extra}: {e}")
        return mtimes

    def _trigger_graceful_restart(self, reason: str) -> None:
        """Request graceful restart without SystemExit traceback."""
        if self._stopping:
            return
        self._stopping = True
        log.info(f"{reason} -> graceful restart (debounce {self.debounce_sec}s)")
        try:
            if self._app is not None:
                self._app.stop_running()
                log.info("Called app.stop_running() for restart")
                return
        except Exception as e:
            log.warning(f"stop_running failed: {e}")
        try:
            os._exit(0)
        except Exception:
            import sys
            sys.exit(0)

    async def _wait_for_idle_and_restart(self, reason: str) -> None:
        """Waits until all active prompt tasks finish before restarting."""
        from ..core.session_manager import session_manager
        # Wait while any task is actively running
        while any(not t.done() for t in session_manager.active_tasks.values()):
            log.info("Watchdog deferring restart: waiting for active tasks to complete...")
            await asyncio.sleep(2.0)
        self._trigger_graceful_restart(reason)

    async def watch_loop(self) -> None:
        """Background loop checking for file changes or restart flag."""
        log.info(f"Watchdog armed: dir={self.watch_dir}, debounce={self.debounce_sec}s, auto_restart={settings.enable_auto_restart}, interval=3s")
        try:
            while True:
                await asyncio.sleep(3.0)

                # 1. Check restart flag (highest priority)
                if self.restart_flag.exists():
                    log.info("Restart flag detected -> restarting process...")
                    try:
                        self.restart_flag.unlink()
                    except Exception as e:
                        log.debug(f"Unlink restart_flag skip: {e}")
                    await asyncio.sleep(0.2)
                    await self._wait_for_idle_and_restart("Restart flag")
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
                for fpath, mtime in current_mtimes.items():
                    prev = self._last_mtimes.get(fpath)
                    if prev is None:
                        changed_path = f"{fpath} (new file)"
                        break
                    if mtime > prev + 0.05:  # 50ms jitter tolerance
                        changed_path = fpath
                        break
                if changed_path is None:
                    for fpath in self._last_mtimes:
                        if fpath not in current_mtimes:
                            changed_path = f"{fpath} (deleted)"
                            break

                if changed_path:
                    log.info(f"File modified: {changed_path} -> debouncing restart {self.debounce_sec}s")
                    await asyncio.sleep(self.debounce_sec)
                    await self._wait_for_idle_and_restart(f"File modified: {changed_path}")
                    return

                self._last_mtimes = current_mtimes
        except asyncio.CancelledError:
            log.info("Watchdog cancelled -- normal shutdown")
            return
        except Exception as e:
            log.error(f"Watchdog fatal error (disabling watchdog, bot stays alive): {e}", exc_info=True)
            return
