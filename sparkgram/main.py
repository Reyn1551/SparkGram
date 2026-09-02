"""
Main Entry Point and Runner for SparkGram.
Includes log rotation (3MB x 3), sensitive token redaction, and graceful watchdog supervisor.
"""
import os
import sys
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import settings
from .bot.app import create_bot_application
from .supervisor.watchdog import FileWatchdog
from .utils.log_masker import mask_sensitive_text


class SensitiveFilter(logging.Filter):
    """Masks bot tokens and API keys in all outgoing log records."""
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_sensitive_text(record.msg)
        if record.args and isinstance(record.args, tuple):
            record.args = tuple(mask_sensitive_text(str(a)) if isinstance(a, str) else a for a in record.args)
        return True


# Configure structured logging with RotatingFileHandler
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
sensitive_filter = SensitiveFilter()

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
console_handler.addFilter(sensitive_filter)

file_handler = RotatingFileHandler(
    settings.log_file,
    maxBytes=3 * 1024 * 1024,  # 3 MB per log file
    backupCount=3,             # Keep 3 backups (max 12 MB total)
    encoding="utf-8",
)
file_handler.setFormatter(log_formatter)
file_handler.addFilter(sensitive_filter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers = [console_handler, file_handler]

log = logging.getLogger("sparkgram")


def _acquire_singleton_lock() -> bool:
    """Prevents duplicate polling instances (creates PID lock file). Returns True if lock acquired."""
    try:
        lock_dir = settings.log_dir
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_file = lock_dir / "bridge.lock"
        current_pid = str(os.getpid())
        if lock_file.exists():
            try:
                old_pid_str = lock_file.read_text(encoding="utf-8").strip()
                if old_pid_str.isdigit():
                    old_pid = int(old_pid_str)
                    # Check if old process still alive (Windows)
                    try:
                        import psutil  # optional
                        if psutil.pid_exists(old_pid):
                            proc = psutil.Process(old_pid)
                            if proc.is_running() and "bot_bridge" in " ".join(proc.cmdline() or []):
                                log.warning(f"Another bridge instance running (PID {old_pid}) — refusing duplicate poll. Killing stale is manual: Stop-Process -Id {old_pid} -Force")
                                return False
                    except ImportError:
                        # Fallback: check via tasklist without psutil
                        import subprocess
                        try:
                            out = subprocess.check_output(f'tasklist /FI "PID eq {old_pid}"', shell=True, text=True)
                            if str(old_pid) in out and "python" in out.lower():
                                log.warning(f"Another bridge instance (PID {old_pid}) still active — refusing duplicate.")
                                return False
                        except Exception:
                            pass
                    # Stale lock (process dead) -> overwrite
                    log.info(f"Overwriting stale lock PID {old_pid} -> {current_pid}")
            except Exception as e:
                log.debug(f"Lock check skip: {e}")
        lock_file.write_text(current_pid, encoding="utf-8")
        # Ensure lock is cleaned on exit
        import atexit
        def _release():
            try:
                if lock_file.exists() and lock_file.read_text(encoding="utf-8").strip() == current_pid:
                    lock_file.unlink(missing_ok=True)
            except Exception:
                pass
        atexit.register(_release)
        return True
    except Exception as e:
        log.debug(f"Singleton lock error: {e}")
        return True


def run_bot():
    """Starts SparkGram bot application with background watchdog."""
    # Singleton guard for polling mode
    if not settings.webhook_url:
        if not _acquire_singleton_lock():
            log.error("Duplicate polling instance detected — exiting to avoid 409 Conflict. Kill old PID via Task Manager or Restart.")
            # Do not start polling; exit gracefully so supervisor doesn't hot-loop
            import time
            time.sleep(5)
            sys.exit(0)
    log.info(f"Starting SparkGram v1.0 (Model: {settings.runtime_model}, WorkDir: {settings.runtime_work_dir})")
    
    app = create_bot_application()
    
    # Setup background tasks on post_init (watchdog & cron scheduler)
    async def post_init(application):
        # 1. Background File Watchdog
        watchdog = FileWatchdog(watch_dir=settings.root_dir, debounce_sec=4.0)
        watchdog.bind_app(application)
        wd_task = asyncio.create_task(watchdog.watch_loop())
        def _wd_done_cb(t: asyncio.Task):
            try:
                exc = t.exception()
                if exc is not None:
                    log.error(f"Watchdog exited with exception: {exc}", exc_info=exc)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                log.error(f"Watchdog done_cb error: {e}")
        wd_task.add_done_callback(_wd_done_cb)
        log.info("File watchdog and self-healing supervisor loop started.")

        # 2. Self-Hosted Cron Scheduler
        from .scheduler.manager import cron_scheduler
        sched_task = asyncio.create_task(cron_scheduler.start_scheduler_loop(application.bot, interval_sec=20))
        def _sched_done_cb(t: asyncio.Task):
            try:
                exc = t.exception()
                if exc is not None:
                    log.error(f"Scheduler exited with exception: {exc}", exc_info=exc)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                log.error(f"Scheduler done_cb error: {e}")
        sched_task.add_done_callback(_sched_done_cb)
        log.info("Self-hosted Cron Scheduler loop started.")

    app.post_init = post_init

    if settings.webhook_url:
        log.info(f"Running in Webhook mode -> {settings.webhook_url}")
        app.run_webhook(
            listen="0.0.0.0",
            port=settings.port,
            url_path="webhook",
            webhook_url=f"{settings.webhook_url}/webhook",
            secret_token=settings.webhook_secret,
        )
    else:
        log.info("Running in Polling mode (development / local machine)")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_bot()
