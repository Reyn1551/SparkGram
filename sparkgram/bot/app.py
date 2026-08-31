"""
Application Builder and Lifecycle Setup for SparkGram Telegram Bot.
"""
import logging
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from ..config import settings
from .handlers import (
    start_cmd,
    id_cmd,
    pwd_cmd,
    model_cmd,
    workdir_cmd,
    sessions_cmd,
    switch_cmd,
    new_cmd,
    status_cmd,
    health_cmd,
    sysinfo_cmd,
    logs_cmd,
    rename_cmd,
    delete_cmd,
    export_cmd,
    cancel_cmd,
    restart_cmd,
    callback_query_handler,
    message_handler,
    voice_handler,
    photo_handler,
)

log = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global exception handler to prevent unhandled error crashes."""
    log.error(f"Unhandled exception in Telegram handler: {context.error}", exc_info=context.error)


def create_bot_application() -> Application:
    """Builds and configures the python-telegram-bot Application."""
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN belum diset di .env atau environment variables.")

    builder = ApplicationBuilder().token(settings.telegram_bot_token)
    app = builder.build()

    # 1. Command Handlers
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", start_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("pwd", pwd_cmd))
    app.add_handler(CommandHandler("health", health_cmd))
    app.add_handler(CommandHandler("sysinfo", sysinfo_cmd))
    app.add_handler(CommandHandler("logs", logs_cmd))
    app.add_handler(CommandHandler("model", model_cmd))
    app.add_handler(CommandHandler("workdir", workdir_cmd))
    app.add_handler(CommandHandler("sessions", sessions_cmd))
    app.add_handler(CommandHandler("switch", switch_cmd))
    app.add_handler(CommandHandler("new", new_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("rename", rename_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("restart", restart_cmd))

    # 2. Callback Query Handler (inline buttons)
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    # 3. Media Handlers
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, photo_handler))

    # 4. Natural Text Message Handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # 5. Global Error Handler
    app.add_error_handler(error_handler)

    return app
