"""
Main Entry Point and Runner for SparkGram.
"""
import sys
import asyncio
import logging
from pathlib import Path

from .config import settings
from .bot.app import create_bot_application
from .supervisor.watchdog import FileWatchdog
from .utils.log_masker import mask_sensitive_text

# Configure structured logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.log_file, encoding="utf-8"),
    ]
)
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
