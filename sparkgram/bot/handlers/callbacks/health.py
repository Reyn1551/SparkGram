"""Health callbacks (hlth:) — extracted from callbacks.py"""
import html
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from ....config import settings
from ....core.session_manager import session_manager


async def handle(query, context, chat_id: int, work_dir: str, payload: str) -> bool:
    payload = payload.strip()

    if payload == "refresh":
        await query.answer("🔄 Memperbarui telemetri hardware...")
        from ....utils.system_monitor import get_system_health, format_health_html, build_health_keyboard
        active_session = session_manager.get_active_session(chat_id)
        is_busy = chat_id in session_manager.active_tasks and not session_manager.active_tasks[chat_id].done()
        data_health = get_system_health()
        text = format_health_html(data_health, active_session=active_session, is_busy=is_busy)
        kb = build_health_keyboard()
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if payload == "model":
        await query.answer("🤖 Membuka daftar model...")
        from ....core.models import build_models_html, build_models_keyboard
        text = build_models_html(settings.runtime_model)
        kb = build_models_keyboard(settings.runtime_model)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if payload == "logs":
        await query.answer("📜 Mengambil 20 baris log terbaru...")
        from ....utils.log_masker import mask_sensitive_text
        log_file = settings.log_file
        if not log_file.exists():
            await context.bot.send_message(chat_id=chat_id, text="<i>Belum ada log yang tersimpan di disk.</i>", parse_mode=ParseMode.HTML)
            return True
        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            tail = all_lines[-20:]
            raw_text = "".join(tail)
            masked_text = mask_sensitive_text(raw_text)
            if len(masked_text) > 3500:
                masked_text = masked_text[-3500:]
            escaped = html.escape(masked_text)
            log_msg_text = f"📜 <b>Tail Log Realtime ({len(tail)} baris):</b>\n<pre><code>{escaped}</code></pre>"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Tutup Pesan Log", callback_data="act:close")]])
            await context.bot.send_message(chat_id=chat_id, text=log_msg_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception as e:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Gagal membaca log: {html.escape(str(e))}", parse_mode=ParseMode.HTML)
        return True

    return False
