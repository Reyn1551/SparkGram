"""
Session Handlers — extracted from commands.py (Hari-1 Opsi B).
Handles /session hub and legacy aliases: /sessions, /switch, /new, /status, /rename, /delete, /export
"""
import html
import time

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ...config import settings
from ...core.session_manager import (
    session_manager,
    build_sessions_html,
    build_sessions_keyboard,
)
from ..middlewares import is_allowed


async def session_hub_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified SESSION: /session [ls|switch|new|rename|delete|export|status]"""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    args = context.args or []
    sub = (args[0].lower() if args else "ls")
    rest = args[1:] if len(args) > 1 else []

    if sub in ("ls", "list", "show", ""):
        query = " ".join(rest).strip() if rest else None
        work_dir = session_manager.get_chat_workdir(chat_id)
        active_id = session_manager.get_active_session(chat_id)
        sessions = await session_manager.fetch_sessions(work_dir=work_dir, limit=30, query=query)
        text = build_sessions_html(sessions, active_id, page=0, page_size=10)
        kb = build_sessions_keyboard(sessions, active_id, page=0, page_size=10)
        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return
    if sub in ("switch", "sw", "use"):
        if not rest:
            work_dir = session_manager.get_chat_workdir(chat_id)
            sessions = await session_manager.fetch_sessions(work_dir=work_dir, limit=10)
            kb = build_sessions_keyboard(sessions, session_manager.get_active_session(chat_id), page=0)
            if update.message:
                await update.message.reply_text("Pilih session untuk di-switch:", reply_markup=kb)
            return
        chosen = rest[0].strip()
        work_dir = session_manager.get_chat_workdir(chat_id)
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
            await update.message.reply_text(f"✅ Session di-switch ke: <code>{html.escape(chosen)}</code>", parse_mode=ParseMode.HTML)
        return
    if sub in ("new", "create", "reset"):
        session_manager.set_active_session(chat_id, None)
        if update.message:
            await update.message.reply_text("🆕 Session di-reset. Pesan berikutnya akan buat session baru.", parse_mode=ParseMode.HTML)
        return
    if sub in ("rename", "title"):
        active = session_manager.get_active_session(chat_id)
        if not active:
            if update.message:
                await update.message.reply_text("❌ Tidak ada session aktif untuk di-rename.", parse_mode=ParseMode.HTML)
            return
        if not rest:
            if update.message:
                await update.message.reply_text("Gunakan: <code>/session rename Judul Baru</code>", parse_mode=ParseMode.HTML)
            return
        new_title = " ".join(rest).strip()
        ok, out = await session_manager.rename_session(active, new_title)
        if update.message:
            if ok:
                await update.message.reply_text(f"✅ Session di-rename ke: <b>{html.escape(new_title)}</b>", parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(f"❌ Gagal rename: {html.escape(out)}", parse_mode=ParseMode.HTML)
        return
    if sub in ("delete", "del", "rm", "remove"):
        target_id = rest[0].strip() if rest else session_manager.get_active_session(chat_id)
        if not target_id:
            if update.message:
                await update.message.reply_text("Gunakan: <code>/session delete ses_xxx</code>", parse_mode=ParseMode.HTML)
            return
        ok, out = await session_manager.delete_session(target_id)
        if update.message:
            if ok:
                await update.message.reply_text(f"🗑️ Session dihapus: <code>{html.escape(target_id)}</code>", parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(f"❌ Gagal hapus: {html.escape(out)}", parse_mode=ParseMode.HTML)
        return
    if sub in ("export", "save", "dump"):
        active = session_manager.get_active_session(chat_id)
        if not active:
            if update.message:
                await update.message.reply_text("❌ Tidak ada session aktif untuk di-export.", parse_mode=ParseMode.HTML)
            return
        ok, filepath, content = await session_manager.export_session_to_markdown(active)
        import os as _os
        if ok and _os.path.exists(filepath):
            if update.message:
                await update.message.reply_document(document=open(filepath, "rb"), caption=f"📄 Export <code>{html.escape(active)}</code>", parse_mode=ParseMode.HTML)
        else:
            if update.message:
                await update.message.reply_text(f"❌ Export gagal: {html.escape(content)}", parse_mode=ParseMode.HTML)
        return
    if sub in ("status", "info"):
        work_dir = session_manager.get_chat_workdir(chat_id)
        active = session_manager.get_active_session(chat_id)
        active_str = f"<code>{html.escape(active)}</code>" if active else "<i>(tidak ada)</i>"
        is_running = chat_id in session_manager.active_tasks and not session_manager.active_tasks[chat_id].done()
        task_label = "🏃 Sibuk" if is_running else "🟢 Idle"
        text = f"📊 <b>SESSION Status</b>\n• Task: {task_label}\n• Session: {active_str}\n• WORK_DIR: <code>{html.escape(work_dir)}</code>\n• Model: <code>{html.escape(settings.runtime_model)}</code>"
        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return
    if update.message:
        await update.message.reply_text("Gunakan: <code>/session [ls|switch|new|rename|delete|export|status]</code>", parse_mode=ParseMode.HTML)


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
    is_task_running = chat_id in session_manager.active_tasks and not session_manager.active_tasks[chat_id].done()
    is_proc_running = chat_id in session_manager.active_procs and getattr(session_manager.active_procs[chat_id], "returncode", None) is None
    is_running = is_task_running or is_proc_running
    if is_running:
        start_t = session_manager.task_start_times.get(chat_id, time.monotonic())
        elapsed = time.monotonic() - start_t
        task_label = f"🏃 <b>Sibuk</b> <i>(Memproses prompt • {elapsed:.1f}s)</i>"
    else:
        task_label = "🟢 <b>Idle</b>"
    status_text = (
        f"📊 <b>SparkGram Status</b>\n\n"
        f"• Task berjalan: {task_label}\n"
        f"• Session aktif: {active_str}\n"
        f"• Model aktif: <code>{html.escape(settings.runtime_model)}</code>\n"
        f"• WORK_DIR: <code>{html.escape(work_dir)}</code>\n"
        f"• Auto Restart: <code>{settings.enable_auto_restart}</code>"
    )
    if update.message:
        await update.message.reply_text(status_text, parse_mode=ParseMode.HTML)


async def rename_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /rename command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    active = session_manager.get_active_session(chat_id)
    if not active:
        if update.message:
            await update.message.reply_text("❌ Tidak ada session aktif untuk di-rename.", parse_mode=ParseMode.HTML)
        return
    args = context.args or []
    if not args:
        if update.message:
            await update.message.reply_text("Gunakan: <code>/rename Judul Baru</code>", parse_mode=ParseMode.HTML)
        return
    new_title = " ".join(args).strip()
    ok, out = await session_manager.rename_session(active, new_title)
    if update.message:
        if ok:
            await update.message.reply_text(f"✅ Session di-rename ke: <b>{html.escape(new_title)}</b>", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"❌ Gagal rename: {html.escape(out)}", parse_mode=ParseMode.HTML)


async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /delete command."""
    if not is_allowed(update):
        return
    target_id = None
    args = context.args or []
    if args:
        target_id = args[0].strip()
    else:
        chat_id = update.effective_chat.id if update.effective_chat else 0
        target_id = session_manager.get_active_session(chat_id)
    if not target_id:
        if update.message:
            await update.message.reply_text("Gunakan: <code>/delete ses_xxx</code>", parse_mode=ParseMode.HTML)
        return
    ok, out = await session_manager.delete_session(target_id)
    if update.message:
        if ok:
            await update.message.reply_text(f"🗑️ Session dihapus: <code>{html.escape(target_id)}</code>", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"❌ Gagal hapus: {html.escape(out)}", parse_mode=ParseMode.HTML)


async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /export command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    active = session_manager.get_active_session(chat_id)
    if not active:
        if update.message:
            await update.message.reply_text("❌ Tidak ada session aktif untuk di-export.", parse_mode=ParseMode.HTML)
        return
    ok, filepath, content = await session_manager.export_session_to_markdown(active)
    import os as _os
    if ok and _os.path.exists(filepath):
        if update.message:
            await update.message.reply_document(document=open(filepath, "rb"), caption=f"📄 Export <code>{html.escape(active)}</code>", parse_mode=ParseMode.HTML)
    else:
        if update.message:
            await update.message.reply_text(f"❌ Export gagal: {html.escape(content)}", parse_mode=ParseMode.HTML)
