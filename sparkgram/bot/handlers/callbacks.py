"""
Inline Callback Query Handlers for SparkGram.
Handles session switching, model selection, hardware telemetri, logs viewer, and actions.
"""
import os
import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ...config import settings
from ...core.session_manager import (
    session_manager,
    build_sessions_html,
    build_sessions_keyboard,
)
from ..middlewares import is_allowed

log = logging.getLogger(__name__)


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispatches button clicks from all inline keyboards."""
    query = update.callback_query
    if not query:
        return

    if not is_allowed(update):
        await query.answer("❌ Akses ditolak. ID kamu tidak terdaftar di whitelist.", show_alert=True)
        return

    data = query.data or ""
    chat_id = update.effective_chat.id if update.effective_chat else 0
    work_dir = session_manager.get_chat_workdir(chat_id)

    # 1. Session Management Callbacks (sw:...)
    if data.startswith("sw:"):
        payload = data[3:]
        
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
            return

        elif payload == "refresh":
            await query.answer("🔄 Memperbarui daftar sesi...")
            active_id = session_manager.get_active_session(chat_id)
            sessions = await session_manager.fetch_sessions(work_dir=work_dir, limit=30)
            text = build_sessions_html(sessions, active_id, page=0)
            kb = build_sessions_keyboard(sessions, active_id, page=0)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif payload.startswith("page:"):
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
            return

        elif payload == "workdir":
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
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Kembali ke Sesi", callback_data="sw:refresh")]
            ])
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        else:
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
            return

    # 2. Model Switcher Callbacks (mod:...)
    elif data.startswith("mod:"):
        from ...core.models import (
            PRESET_MODELS,
            find_preset_model,
            build_models_html,
            build_models_keyboard,
        )
        mod_id = data[4:].strip()
        matched = find_preset_model(mod_id)
        if matched:
            new_model = matched["model"]
            settings.runtime_model = new_model
            session_manager.save_state()
            await query.answer(f"✅ Model diubah ke: {matched['name']}", show_alert=False)
            text = build_models_html(settings.runtime_model)
            kb = build_models_keyboard(settings.runtime_model)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return
        else:
            await query.answer("❌ Model tidak ditemukan.", show_alert=True)
            return

    # 3. System Health Telemetry Callbacks (hlth:...)
    elif data.startswith("hlth:"):
        payload = data[5:].strip()
        
        if payload == "refresh":
            await query.answer("🔄 Memperbarui telemetri hardware...")
            from ...utils.system_monitor import get_system_health, format_health_html, build_health_keyboard
            active_session = session_manager.get_active_session(chat_id)
            is_busy = chat_id in session_manager.active_tasks and not session_manager.active_tasks[chat_id].done()
            data_health = get_system_health()
            text = format_health_html(data_health, active_session=active_session, is_busy=is_busy)
            kb = build_health_keyboard()
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif payload == "model":
            await query.answer("🤖 Membuka daftar model...")
            from ...core.models import build_models_html, build_models_keyboard
            text = build_models_html(settings.runtime_model)
            kb = build_models_keyboard(settings.runtime_model)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif payload == "logs":
            await query.answer("📜 Mengambil 20 baris log terbaru...")
            from ...utils.log_masker import mask_sensitive_text
            log_file = settings.log_file
            if not log_file.exists():
                await context.bot.send_message(chat_id=chat_id, text="<i>Belum ada log yang tersimpan di disk.</i>", parse_mode=ParseMode.HTML)
                return
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
                # Send as new message so it never collides with active streaming loop
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=log_msg_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                )
            except Exception as e:
                await context.bot.send_message(chat_id=chat_id, text=f"❌ Gagal membaca log: {html.escape(str(e))}", parse_mode=ParseMode.HTML)
            return

    # 4. Action Button Callbacks (act:...)
    elif data.startswith("act:"):
        payload = data[4:].strip()
        
        if payload == "cancel":
            from ...engine.process_tree import process_supervisor
            cancelled_any = False
            proc = session_manager.active_procs.pop(chat_id, None)
            if proc:
                await process_supervisor.kill_process_tree(proc)
                cancelled_any = True

            task = session_manager.active_tasks.pop(chat_id, None)
            if task and not task.done():
                task.cancel()
                cancelled_any = True

            if cancelled_any:
                await query.answer("🛑 Job dibatalkan.", show_alert=False)
                try:
                    await query.edit_message_text(
                        "🛑 <b>Job berhasil dibatalkan oleh pengguna via tombol.</b>\n<i>Subproses telah dimatikan secara bersih.</i>",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
            else:
                await query.answer("Tidak ada job aktif yang sedang berjalan.", show_alert=True)
            return

        elif payload == "close":
            await query.answer("🗑️ Pesan ditutup.")
            try:
                await query.message.delete()
            except Exception:
                try:
                    await query.edit_message_text("<i>(Pesan ditutup)</i>", parse_mode=ParseMode.HTML)
                except Exception:
                    pass
            return

    await query.answer()
