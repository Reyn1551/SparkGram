"""
Inline Callback Query Dispatcher for SparkGram — Modular (Opsi B+).
Routes prefix-based callbacks to dedicated subhandlers for easy maintenance.
Each prefix lives in its own file (1 prefix = 1 file).
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes

from ....core.session_manager import session_manager
from ...middlewares import is_allowed

log = logging.getLogger(__name__)


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispatches button clicks from all inline keyboards to modular subhandlers."""
    query = update.callback_query
    if not query:
        return

    if not is_allowed(update):
        await query.answer("❌ Akses ditolak. ID kamu tidak terdaftar di whitelist.", show_alert=True)
        return

    data = query.data or ""
    chat_id = update.effective_chat.id if update.effective_chat else 0
    work_dir = session_manager.get_chat_workdir(chat_id)

    try:
        if data.startswith("sw:"):
            from .session import handle as h
            await h(query, context, chat_id, work_dir, data[3:])
            return

        if data.startswith("mod:"):
            from .model import handle as h
            await h(query, context, chat_id, work_dir, data[4:])
            return

        if data.startswith("hlth:"):
            from .health import handle as h
            await h(query, context, chat_id, work_dir, data[5:])
            return

        if data.startswith("act:"):
            from .action import handle as h
            await h(query, context, chat_id, work_dir, data[4:])
            return

        if data.startswith("git:"):
            from .git import handle as h
            await h(query, context, chat_id, work_dir, data[4:])
            return

        if data.startswith("mem:"):
            from .memory import handle as h
            await h(query, context, chat_id, work_dir, data[4:])
            return

        if data.startswith("job:"):
            from .scheduler import handle as h
            await h(query, context, chat_id, work_dir, data[4:])
            return

        if data.startswith("macro:"):
            from .recipe import handle as h
            await h(query, context, chat_id, work_dir, data[6:], update)  # type: ignore
            return

        if data.startswith("fe:"):
            from .files import handle as h
            await h(query, context, chat_id, work_dir, data[3:])
            return

        if data.startswith("pw:"):
            from .preview import handle as h
            await h(query, context, chat_id, work_dir, data[3:])
            return

        if data.startswith("port:"):
            from .ports import handle as h
            await h(query, context, chat_id, work_dir, data[5:])
            return

        # Unknown prefix — acknowledge to remove loading spinner
        await query.answer()

    except Exception as e:
        log.warning(f"Callback handler error for {data[:30]}: {e}", exc_info=True)
        try:
            await query.answer("❌ Terjadi kesalahan, coba lagi.", show_alert=True)
        except Exception:
            pass
