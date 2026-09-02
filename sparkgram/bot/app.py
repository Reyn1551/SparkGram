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
    memory_cmd,
    health_cmd,
    sysinfo_cmd,
    logs_cmd,
    rename_cmd,
    delete_cmd,
    export_cmd,
    cancel_cmd,
    restart_cmd,
    git_cmd,
    diff_cmd,
    commit_cmd,
    push_cmd,
    macro_cmd,
    review_cmd,
    testgen_cmd,
    explain_cmd,
    refactor_cmd,
    files_cmd,
    cat_cmd,
    download_cmd,
    preview_cmd,
    ports_cmd,
    killport_cmd,
    schedule_cmd,
    jobs_cmd,
    unschedule_cmd,
    # ULTRA unified hubs
    nav_cmd,
    session_hub_cmd,
    sys_hub_cmd,
    jobs_hub_cmd,
    git_hub_cmd,
    recipe_hub_cmd,
    callback_query_handler,
    message_handler,
    voice_handler,
    photo_handler,
    document_handler,
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

    # === ULTRA 8 CORE (visible in /help) ===
    app.add_handler(CommandHandler("nav", nav_cmd))
    app.add_handler(CommandHandler("session", session_hub_cmd))
    app.add_handler(CommandHandler("git", git_hub_cmd))
    app.add_handler(CommandHandler("recipe", recipe_hub_cmd))
    app.add_handler(CommandHandler("sys", sys_hub_cmd))
    app.add_handler(CommandHandler("jobs", jobs_hub_cmd))
    app.add_handler(CommandHandler("model", model_cmd))
    app.add_handler(CommandHandler("memory", memory_cmd))
    # Essentials
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", start_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("restart", restart_cmd))

    # === DEPRECATED ALIASES (hidden, not in /help) — keep for backward compat, will be removed ===
    app.add_handler(CommandHandler("workdir", workdir_cmd))
    app.add_handler(CommandHandler("files", files_cmd))
    app.add_handler(CommandHandler("tree", files_cmd))
    app.add_handler(CommandHandler("pwd", pwd_cmd))
    app.add_handler(CommandHandler("cat", cat_cmd))
    app.add_handler(CommandHandler("download", download_cmd))
    app.add_handler(CommandHandler("sessions", sessions_cmd))
    app.add_handler(CommandHandler("switch", switch_cmd))
    app.add_handler(CommandHandler("new", new_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("health", health_cmd))
    app.add_handler(CommandHandler("sysinfo", sysinfo_cmd))
    app.add_handler(CommandHandler("logs", logs_cmd))
    app.add_handler(CommandHandler("preview", preview_cmd))
    app.add_handler(CommandHandler("snap", preview_cmd))
    app.add_handler(CommandHandler("ports", ports_cmd))
    app.add_handler(CommandHandler("killport", killport_cmd))
    app.add_handler(CommandHandler("schedule", schedule_cmd))
    app.add_handler(CommandHandler("unschedule", unschedule_cmd))
    app.add_handler(CommandHandler("rename", rename_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CommandHandler("export", export_cmd))
    # Git shortcuts deprecated → use /git
    app.add_handler(CommandHandler("diff", diff_cmd))
    app.add_handler(CommandHandler("commit", commit_cmd))
    app.add_handler(CommandHandler("push", push_cmd))
    # Recipe shortcuts deprecated → use /recipe
    app.add_handler(CommandHandler("macro", macro_cmd))
    app.add_handler(CommandHandler("review", review_cmd))
    app.add_handler(CommandHandler("testgen", testgen_cmd))
    app.add_handler(CommandHandler("explain", explain_cmd))
    app.add_handler(CommandHandler("refactor", refactor_cmd))

    # 6. Callback Query Handler (inline buttons)
    app.add_handler(CallbackQueryHandler(callback_query_handler))

    # 7. Media & Document Handlers
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, photo_handler))
    app.add_handler(MessageHandler(filters.Document.ALL & ~filters.Document.IMAGE, document_handler))

    # 7. Natural Text Message Handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # 8. Global Error Handler
    app.add_error_handler(error_handler)

    return app
