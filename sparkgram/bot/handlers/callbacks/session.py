"""Session callbacks (sw:) — extracted from callbacks.py"""
import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from ....config import settings
from ....core.session_manager import session_manager, build_sessions_html, build_sessions_keyboard


async def handle(query, context, chat_id: int, work_dir: str, payload: str) -> bool:
    """Handles sw: payload. Returns True if handled."""
    if payload == "new":
        session_manager.set_active_session(chat_id, None)
        await query.answer("🆕 Session baru disiapkan! Pesan berikutnya akan membuat konteks baru.")
        sessions = await session_manager.fetch_sessions(work_dir=work_dir, limit=30)
        text = build_sessions_html(sessions, None, page=0)
        kb = build_sessions_keyboard(sessions, None, page=0)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if payload == "refresh":
        await query.answer("🔄 Memperbarui daftar sesi...")
        active_id = session_manager.get_active_session(chat_id)
        sessions = await session_manager.fetch_sessions(work_dir=work_dir, limit=30)
        text = build_sessions_html(sessions, active_id, page=0)
        kb = build_sessions_keyboard(sessions, active_id, page=0)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if payload.startswith("page:"):
        try:
            page_num = int(payload.split(":")[1])
        except Exception:
            page_num = 0
        await query.answer(f"Halaman {page_num + 1}")
        active_id = session_manager.get_active_session(chat_id)
        sessions = await session_manager.fetch_sessions(work_dir=work_dir, limit=30)
        text = build_sessions_html(sessions, active_id, page=page_num)
        kb = build_sessions_keyboard(sessions, active_id, page=page_num)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if payload == "workdir":
        await query.answer("📁 Ganti direktori proyek")
        cur_dir = html.escape(session_manager.get_chat_workdir(chat_id))
        text = (
            f"📁 <b>WORK_DIR Proyek Chat Ini:</b>\n"
            f"<code>{cur_dir}</code>\n\n"
            f"Untuk mengganti folder proyek, kirim perintah:\n"
            f"<code>/workdir C:\\Path\\Ke\\Project\\Kamu</code>\n\n"
            f"Atau reset ke default:\n"
            f"<code>/workdir default</code>"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀ Kembali ke Sesi", callback_data="sw:refresh")]])
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    # Switch to specific session_id
    chosen_sid = payload
    session_manager.set_active_session(chat_id, chosen_sid)
    short_id = chosen_sid[-6:] if len(chosen_sid) > 6 else chosen_sid
    await query.answer(f"✅ Switch ke sesi: {short_id}")
    sessions = await session_manager.fetch_sessions(work_dir=work_dir, limit=30)
    text = build_sessions_html(sessions, chosen_sid, page=0)
    kb = build_sessions_keyboard(sessions, chosen_sid, page=0)
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception:
        pass
    return True
