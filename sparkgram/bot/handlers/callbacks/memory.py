"""Memory callbacks (mem:) — extracted from callbacks.py"""
import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode


async def handle(query, context, chat_id: int, work_dir: str, payload: str) -> bool:
    from ....memory.manager import memory_manager
    payload = payload.strip()

    if payload == "recent":
        await query.answer("🧠 Memuat memory terbaru...")
        recent = memory_manager.recent(days=7, limit=20)
        stats = memory_manager.stats()
        if not recent:
            text = f"🧠 <b>Persistent Memory</b> — {stats['files']} file(s)\n<i>Belum ada memory.</i>"
        else:
            inner = "\n".join(html.escape(l) for l in recent)
            text = f"🧠 <b>Persistent Memory</b> — {stats['files']} file(s), {stats['lines']} baris\n<blockquote expandable>\n{inner}\n</blockquote>"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔍 Search", callback_data="mem:search"), InlineKeyboardButton("🗑️ Cleanup", callback_data="mem:cleanup")]])
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if payload == "search":
        await query.answer("Ketik /memory kata_kunci untuk search")
        await context.bot.send_message(chat_id=chat_id, text="🔍 <b>Memory Search:</b>\nKirim <code>/memory kata_kunci</code> untuk cari memory.\nContoh: <code>/memory refactor</code>", parse_mode=ParseMode.HTML)
        return True

    if payload == "cleanup":
        deleted = memory_manager.cleanup(keep_days=30)
        await query.answer(f"🗑️ {deleted} file lama dihapus" if deleted else "Tidak ada file lama", show_alert=True)
        return True

    return False
