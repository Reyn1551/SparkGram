"""
Main Entry Point and Runner for SparkGram.
Includes log rotation (3MB x 3), sensitive token redaction, and graceful watchdog supervisor.
"""
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


def run_bot():
    """Starts SparkGram bot application with background watchdog."""
    log.info(f"Starting SparkGram v1.0 (Model: {settings.runtime_model}, WorkDir: {settings.runtime_work_dir})")
    
    app = create_bot_application()
    
    # Setup background file watchdog task on post_init with graceful binding
    async def post_init(application):
        watchdog = FileWatchdog(watch_dir=settings.root_dir, debounce_sec=4.0)
        watchdog.bind_app(application)
        task = asyncio.create_task(watchdog.watch_loop())
        def _done_cb(t: asyncio.Task):
            try:
                exc = t.exception()
                if exc is not None:
                    log.error(f"Watchdog exited with exception: {exc}", exc_info=exc)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                log.error(f"Watchdog done_cb error: {e}")
        task.add_done_callback(_done_cb)
        log.info("File watchdog and self-healing supervisor loop started.")

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
