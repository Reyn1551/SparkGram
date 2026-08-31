"""
Telegram Slash Command Handlers for SparkGram.
"""
import os
import sys
import html
import time
import shutil
import logging
from pathlib import Path
from typing import List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ...config import settings
from ...core.session_manager import (
    session_manager,
    build_sessions_html,
    build_sessions_keyboard,
)
from ...engine.process_tree import process_supervisor
from ..middlewares import is_allowed

log = logging.getLogger(__name__)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start and /help commands."""
    if not is_allowed(update):
        if update.message and update.effective_user:
            await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return

    mode = "webhook" if settings.webhook_url else "polling"
    chat_id = update.effective_chat.id if update.effective_chat else 0
    active = session_manager.get_active_session(chat_id)
    active_str = f"<code>{html.escape(active)}</code> ✅" if active else "<i>(belum ada — pesan baru akan buat session)</i>"
    current_workdir = session_manager.get_chat_workdir(chat_id)

    help_text = (
        f"✨ <b>SparkGram AI Bridge Aktif</b> • <code>{html.escape(settings.runtime_model)}</code>\n\n"
        f"WORK_DIR: <code>{html.escape(current_workdir)}</code>\n"
        f"Session aktif: {active_str}\n"
        f"Mode: <code>{mode}</code> {'('+html.escape(settings.webhook_url)+')' if settings.webhook_url else '(dev, laptop harus nyala)'}\n"
        f"Model: <code>{html.escape(settings.runtime_model)}</code>\n\n"
        f"Kirim prompt langsung untuk coding atau refactoring.\n"
        f"Contoh: <i>buatkan unit test untuk auth service</i>\n\n"
        f"<b>Daftar Perintah:</b>\n"
        f"/health - status lengkap hardware laptop/PC (CPU, RAM, Disk, Baterai, GPU)\n"
        f"/model [list|1-7] - pilih model AI 1-tap (Spark, Groq, DeepSeek, Claude, dll)\n"
        f"/sessions [n] [kata] - list session di WORK_DIR (tap nomor untuk switch)\n"
        f"/switch [n|ses_xxx] - ganti session aktif\n"
        f"/workdir [path|list] - ganti/lihat project directory\n"
        f"/new - session baru (reset konteks)\n"
        f"/status - status queue & runtime\n"
        f"/rename [judul] - rename session aktif\n"
        f"/delete [ses_xxx] - hapus session\n"
        f"/fork [pesan] - fork session aktif\n"
        f"/export - export session ke file Markdown\n"
        f"/logs [n] - tail log bridge\n"
        f"/cancel - batalkan job yang sedang berjalan\n"
        f"/pwd /id /restart /help"
    )

    if update.message:
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /id command."""
    if not is_allowed(update):
        if update.message and update.effective_user:
            await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    if update.message and update.effective_chat and update.effective_user:
        await update.message.reply_text(
            f"chat_id: <code>{update.effective_chat.id}</code>\n"
            f"user_id: <code>{update.effective_user.id}</code>",
            parse_mode=ParseMode.HTML,
        )


async def pwd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /pwd command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    active = session_manager.get_active_session(chat_id)
    active_str = f"\nSession aktif: <code>{html.escape(active)}</code>" if active else ""
    current_workdir = session_manager.get_chat_workdir(chat_id)
    if update.message:
        await update.message.reply_text(
            f"WORK_DIR: <code>{html.escape(current_workdir)}</code>{active_str}\n"
            f"<i>Base WORK_DIR: <code>{html.escape(settings.work_dir)}</code></i>",
            parse_mode=ParseMode.HTML,
        )


async def model_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /model command with interactive 1-tap buttons and quick shortcuts."""
    if not is_allowed(update):
        return

    from ...core.models import (
        PRESET_MODELS,
        find_preset_model,
        build_models_html,
        build_models_keyboard,
    )

    args = context.args or []
    if not args:
        # Show interactive list and 1-tap inline keyboard
        if update.message:
            text = build_models_html(settings.runtime_model)
            kb = build_models_keyboard(settings.runtime_model)
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    sub = args[0].strip()

    # 1. Quick selector by number or alias: /model 1, /model spark, /model 2, /model groq
    preset = find_preset_model(sub)
    if preset:
        new_model = preset["model"]
        settings.runtime_model = new_model
        session_manager.save_state()
        if update.message:
            text = (
                f"✅ Model aktif diubah ke:\n"
                f"<b>{html.escape(preset['name'])}</b>\n"
                f"<code>{html.escape(new_model)}</code>"
            )
            kb = build_models_keyboard(settings.runtime_model)
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # 2. Subcommand: /model list
    if sub.lower() == "list":
        if update.message:
            text = build_models_html(settings.runtime_model)
            kb = build_models_keyboard(settings.runtime_model)
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # 3. Subcommand: /model set <custom_model>
    if sub.lower() == "set" and len(args) >= 2:
        target = args[1].strip()
        matched = find_preset_model(target)
        new_model = matched["model"] if matched else target
        settings.runtime_model = new_model
        session_manager.save_state()
        if update.message:
            label = matched["name"] if matched else new_model
            text = f"✅ Model diubah ke: <b>{html.escape(label)}</b>\n<code>{html.escape(new_model)}</code>"
            kb = build_models_keyboard(settings.runtime_model)
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # 4. Direct custom model string: /model provider/model
    if "/" in sub:
        settings.runtime_model = sub
        session_manager.save_state()
        if update.message:
            text = f"✅ Model diubah ke: <code>{html.escape(sub)}</code>"
            kb = build_models_keyboard(settings.runtime_model)
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if update.message:
        await update.message.reply_text(
            "Gunakan nomor pilihan: <code>/model 1</code> (Spark), <code>/model 2</code> (Groq), atau tap tombol di <code>/model</code>",
            parse_mode=ParseMode.HTML,
        )


async def workdir_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /workdir command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    args = context.args or []

    if not args:
        current_workdir = session_manager.get_chat_workdir(chat_id)
        active = session_manager.get_active_session(chat_id)
        active_str = f"\nSession: <code>{html.escape(active)}</code>" if active else ""
        if update.message:
            await update.message.reply_text(
                f"📁 <b>WORK_DIR Chat Ini:</b>\n<code>{html.escape(current_workdir)}</code>{active_str}\n\n"
                f"Ganti direktori: <code>/workdir C:\\Path\\Folder</code>\n"
                f"Reset default: <code>/workdir default</code>\n"
                f"List session per folder: <code>/workdir list</code>",
                parse_mode=ParseMode.HTML,
            )
        return

    target = " ".join(args).strip()
    if target.lower() == "default":
        session_manager.set_chat_workdir(chat_id, settings.work_dir)
        if update.message:
            await update.message.reply_text(f"✅ WORK_DIR di-reset ke default: <code>{html.escape(settings.work_dir)}</code>", parse_mode=ParseMode.HTML)
        return

    p = Path(target)
    if not p.exists():
        if update.message:
            await update.message.reply_text(f"❌ Path tidak ditemukan: <code>{html.escape(str(p))}</code>", parse_mode=ParseMode.HTML)
        return
    if not p.is_dir():
        if update.message:
            await update.message.reply_text(f"❌ Path bukan direktori: <code>{html.escape(str(p))}</code>", parse_mode=ParseMode.HTML)
        return

    session_manager.set_chat_workdir(chat_id, str(p.resolve()))
    if update.message:
        await update.message.reply_text(f"✅ WORK_DIR chat ini diganti ke:\n<code>{html.escape(str(p.resolve()))}</code>", parse_mode=ParseMode.HTML)


async def sessions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /sessions command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    work_dir = session_manager.get_chat_workdir(chat_id)
    active_id = session_manager.get_active_session(chat_id)

    args = context.args or []
    query = " ".join(args).strip() if args else None

    sessions = await session_manager.fetch_sessions(work_dir=work_dir, limit=30, query=query)
    text = build_sessions_html(sessions, active_id, page=0, page_size=10)
    kb = build_sessions_keyboard(sessions, active_id, page=0, page_size=10)

    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def switch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /switch command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    work_dir = session_manager.get_chat_workdir(chat_id)
    args = context.args or []

    if not args:
        sessions = await session_manager.fetch_sessions(work_dir=work_dir, limit=10)
        kb = build_sessions_keyboard(sessions, session_manager.get_active_session(chat_id), page=0)
        if update.message:
            await update.message.reply_text("Pilih session untuk di-switch:", reply_markup=kb)
        return

    chosen = args[0].strip()
    if chosen.isdigit():
        idx = int(chosen)
        sessions = await session_manager.fetch_sessions(work_dir=work_dir, limit=30)
        if 1 <= idx <= len(sessions):
            chosen = sessions[idx - 1].get("id", "")
        else:
            if update.message:
                await update.message.reply_text(f"❌ Nomor {idx} di luar jangkauan (1..{len(sessions)})", parse_mode=ParseMode.HTML)
            return

    session_manager.set_active_session(chat_id, chosen)
    if update.message:
        await update.message.reply_text(f"✅ Session aktif di-switch ke: <code>{html.escape(chosen)}</code>", parse_mode=ParseMode.HTML)


async def new_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /new command to reset session context."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    session_manager.set_active_session(chat_id, None)
    if update.message:
        await update.message.reply_text("🆕 Session di-reset. Pesan berikutnya akan membuat session baru secara otomatis.", parse_mode=ParseMode.HTML)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /status command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    work_dir = session_manager.get_chat_workdir(chat_id)
    active = session_manager.get_active_session(chat_id)
    active_str = f"<code>{html.escape(active)}</code>" if active else "<i>(tidak ada)</i>"
    is_running = chat_id in session_manager.active_tasks and not session_manager.active_tasks[chat_id].done()

    status_text = (
        f"📊 <b>SparkGram Status</b>\n\n"
        f"• Task berjalan: <b>{'🏃 Sibuk (Job Running)' if is_running else '🟢 Idle'}</b>\n"
        f"• Session aktif: {active_str}\n"
        f"• Model aktif: <code>{html.escape(settings.runtime_model)}</code>\n"
        f"• WORK_DIR: <code>{html.escape(work_dir)}</code>\n"
        f"• Auto Restart: <code>{settings.enable_auto_restart}</code>"
    )
    if update.message:
        await update.message.reply_text(status_text, parse_mode=ParseMode.HTML)


async def health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /health command: full hardware & laptop/PC telemetry."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    active_session = session_manager.get_active_session(chat_id)
    is_busy = chat_id in session_manager.active_tasks and not session_manager.active_tasks[chat_id].done()

    from ...utils.system_monitor import get_system_health, format_health_html, build_health_keyboard
    data = get_system_health()
    text = format_health_html(data, active_session=active_session, is_busy=is_busy)
    kb = build_health_keyboard()

    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def sysinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alias for /health."""
    await health_cmd(update, context)


async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /logs command to tail bridge logs."""
    if not is_allowed(update):
        return
    args = context.args or []
    lines_count = int(args[0]) if args and args[0].isdigit() else 25
    lines_count = max(5, min(100, lines_count))

    from ...utils.log_masker import mask_sensitive_text
    log_file = settings.log_file
    if not log_file.exists():
        if update.message:
            await update.message.reply_text("<i>Belum ada log tercatat.</i>", parse_mode=ParseMode.HTML)
        return

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        tail = all_lines[-lines_count:]
        raw_text = "".join(tail)
        masked_text = mask_sensitive_text(raw_text)
        escaped = html.escape(masked_text)
        if update.message:
            await update.message.reply_text(
                f"📜 <b>Tail Log ({len(tail)} baris):</b>\n<pre><code>{escaped}</code></pre>",
                parse_mode=ParseMode.HTML,
            )
    except Exception as e:
        if update.message:
            await update.message.reply_text(f"❌ Gagal membaca log: {html.escape(str(e))}", parse_mode=ParseMode.HTML)


async def rename_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /rename command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    active = session_manager.get_active_session(chat_id)
    if not active:
        if update.message:
            await update.message.reply_text("❌ Tidak ada session aktif untuk di-rename. Gunakan /sessions.", parse_mode=ParseMode.HTML)
        return
    args = context.args or []
    if not args:
        if update.message:
            await update.message.reply_text("Gunakan: <code>/rename Judul Baru Session</code>", parse_mode=ParseMode.HTML)
        return
    new_title = " ".join(args).strip()
    ok, out = await session_manager.rename_session(active, new_title)
    if ok:
        if update.message:
            await update.message.reply_text(f"✅ Session di-rename ke:\n<b>{html.escape(new_title)}</b>", parse_mode=ParseMode.HTML)
    else:
        if update.message:
            await update.message.reply_text(f"❌ Gagal rename: {html.escape(out)}", parse_mode=ParseMode.HTML)


async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /delete command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    args = context.args or []
    target_id = args[0].strip() if args else session_manager.get_active_session(chat_id)
    if not target_id:
        if update.message:
            await update.message.reply_text("Gunakan: <code>/delete ses_xxx</code> atau pilih session aktif.", parse_mode=ParseMode.HTML)
        return
    ok, out = await session_manager.delete_session(target_id)
    if ok:
        if update.message:
            await update.message.reply_text(f"🗑️ Session dihapus: <code>{html.escape(target_id)}</code>", parse_mode=ParseMode.HTML)
    else:
        if update.message:
            await update.message.reply_text(f"❌ Gagal hapus: {html.escape(out)}", parse_mode=ParseMode.HTML)


async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /export command to export active session to Markdown document."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    active = session_manager.get_active_session(chat_id)
    if not active:
        if update.message:
            await update.message.reply_text("❌ Tidak ada session aktif untuk di-export.", parse_mode=ParseMode.HTML)
        return
    ok, filepath, content = await session_manager.export_session_to_markdown(active)
    if ok and os.path.exists(filepath):
        if update.message:
            await update.message.reply_document(
                document=open(filepath, "rb"),
                caption=f"📄 Export Session <code>{html.escape(active)}</code>",
                parse_mode=ParseMode.HTML,
            )
    else:
        if update.message:
            await update.message.reply_text(f"❌ Export gagal: {html.escape(content)}", parse_mode=ParseMode.HTML)


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /cancel command to abort active running job immediately."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    cancelled_any = False

    # 1. Kill active subprocess if tracked
    proc = session_manager.active_procs.pop(chat_id, None)
    if proc:
        await process_supervisor.kill_process_tree(proc)
        cancelled_any = True

    # 2. Cancel active asyncio task
    task = session_manager.active_tasks.pop(chat_id, None)
    if task and not task.done():
        task.cancel()
        cancelled_any = True

    if cancelled_any:
        if update.message:
            await update.message.reply_text("🛑 <b>Job aktif berhasil dibatalkan & subprocess dibersihkan.</b>", parse_mode=ParseMode.HTML)
    else:
        if update.message:
            await update.message.reply_text("ℹ️ Tidak ada job aktif yang sedang berjalan.", parse_mode=ParseMode.HTML)


async def restart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /restart command."""
    if not is_allowed(update):
        return
    if update.message:
        await update.message.reply_text("♻️ <b>Restarting SparkGram bridge...</b>", parse_mode=ParseMode.HTML)
    # Touch restart flag
    flag = settings.root_dir / ".restart"
    try:
        flag.touch()
    except Exception:
        pass
    # Exit process cleanly to allow supervisor to restart
    sys.exit(0)
