"""
Telegram Slash Command Handlers for SparkGram.
NOTE v2 refactor: this 86KB monolith is retained for backward compat.
Future split target: handlers/nav.py, session.py, sys.py, git.py, recipe.py, jobs.py
All markdown rendering must use formatters.markdown_html (single source, no bot_bridge.py dup).
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
from ...core.git_manager import GitManager
from ...core.macro_manager import macro_manager
from ...engine.file_explorer import file_explorer, state_cache
from ...engine.playwright_preview import playwright_preview, VIEWPORT_PRESETS
from ...engine.port_manager import port_manager
from ...engine.process_tree import process_supervisor
from ..middlewares import is_allowed

# === Modular split (Hari-1 Opsi B) ===
from .nav import pwd_cmd, workdir_cmd, nav_cmd
from .session import (
    session_hub_cmd,
    sessions_cmd,
    switch_cmd,
    new_cmd,
    status_cmd,
    rename_cmd,
    delete_cmd,
    export_cmd,
)

log = logging.getLogger(__name__)


"""
JOBS Handlers — extracted from commands.py (Hari-2 Opsi B).
"""

# ----------------------------------------------------------------
async def jobs_hub_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified JOBS: /jobs [ls|add|rm|run] — scheduler"""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    args = context.args or []
    if not args:
        # ls
        from ...scheduler.manager import cron_scheduler
        jobs = cron_scheduler.list_jobs(chat_id)
        text = cron_scheduler.format_jobs_html(jobs, chat_id=chat_id)
        kb = cron_scheduler.build_jobs_keyboard(jobs, chat_id=chat_id)
        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return
    sub = args[0].lower()
    rest = args[1:]
    if sub in ("ls", "list", "show"):
        from ...scheduler.manager import cron_scheduler
        jobs = cron_scheduler.list_jobs(chat_id)
        text = cron_scheduler.format_jobs_html(jobs, chat_id=chat_id)
        kb = cron_scheduler.build_jobs_keyboard(jobs, chat_id=chat_id)
        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return
    if sub in ("add", "create", "schedule"):
        # Expect: cron_expr + prompt
        if not rest:
            if update.message:
                await update.message.reply_text("Gunakan: <code>/jobs add 0 9 * * * prompt</code> atau <code>/jobs add @hourly prompt</code>", parse_mode=ParseMode.HTML)
            return
        # Reuse schedule logic: delegate to schedule_cmd by faking context
        # Build fake context with args = rest
        fake_ctx = type("obj", (object,), {"args": rest})()
        await schedule_cmd(update, fake_ctx)
        return
    if sub in ("rm", "remove", "del", "delete", "unschedule"):
        if not rest:
            if update.message:
                await update.message.reply_text("Gunakan: <code>/jobs rm job_xxx</code>", parse_mode=ParseMode.HTML)
            return
        job_id = rest[0].strip()
        from ...scheduler.manager import cron_scheduler
        ok = cron_scheduler.remove_job(job_id, chat_id=chat_id)
        if update.message:
            if ok:
                await update.message.reply_text(f"🗑️ Job <code>{html.escape(job_id)}</code> dihapus.", parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(f"❌ Job <code>{html.escape(job_id)}</code> tidak ditemukan.", parse_mode=ParseMode.HTML)
        return
    if sub in ("run", "exec"):
        if not rest:
            if update.message:
                await update.message.reply_text("Gunakan: <code>/jobs run job_xxx</code>", parse_mode=ParseMode.HTML)
            return
        job_id = rest[0].strip()
        from ...scheduler.manager import cron_scheduler
        import asyncio as _asyncio
        job = cron_scheduler.get_job(job_id)
        if job:
            if update.message:
                await update.message.reply_text(f"🚀 Menjalankan <code>{html.escape(job_id)}</code>...", parse_mode=ParseMode.HTML)
            _asyncio.create_task(cron_scheduler.execute_job(context.bot, job))
        else:
            if update.message:
                await update.message.reply_text(f"❌ Job <code>{html.escape(job_id)}</code> tidak ditemukan.", parse_mode=ParseMode.HTML)
        return
    if update.message:
        await update.message.reply_text("Gunakan: <code>/jobs [ls|add|rm|run]</code>", parse_mode=ParseMode.HTML)


async def schedule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /schedule [cron_expr] [prompt] command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    from ...scheduler.manager import cron_scheduler

    args = context.args or []
    if not args:
        jobs = cron_scheduler.list_jobs(chat_id)
        text = cron_scheduler.format_jobs_html(jobs, chat_id=chat_id)
        kb = cron_scheduler.build_jobs_keyboard(jobs, chat_id=chat_id)
        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # Parse arguments:
    # 1. Shortcut: /schedule @hourly prompt...
    # 2. Shortcut: /schedule @every 15m prompt...
    # 3. 5-Field Cron: /schedule 0 9 * * * prompt...
    if args[0].lower() == "@every" and len(args) >= 3:
        cron_expr = f"{args[0]} {args[1]}"
        prompt = " ".join(args[2:]).strip()
    elif args[0].startswith("@") and len(args) >= 2:
        cron_expr = args[0]
        prompt = " ".join(args[1:]).strip()
    elif len(args) >= 6:
        cron_expr = " ".join(args[:5])
        prompt = " ".join(args[5:]).strip()
    else:
        err_text = (
            "⚠️ <b>Format /schedule tidak lengkap.</b>\n\n"
            "<b>Format yang didukung:</b>\n"
            "• <code>/schedule 0 9 * * * Cek git status dan test</code>\n"
            "• <code>/schedule */30 * * * * Health check server</code>\n"
            "• <code>/schedule @hourly Cek port dan memory usage</code>\n"
            "• <code>/schedule @daily Buat rekap commit harian</code>\n"
            "• <code>/schedule @every 15m Ping local dev server</code>\n\n"
            "<i>Ketik <code>/jobs</code> untuk melihat daftar tugas terjadwal.</i>"
        )
        if update.message:
            await update.message.reply_text(err_text, parse_mode=ParseMode.HTML)
        return

    work_dir = session_manager.get_chat_workdir(chat_id)
    try:
        job = cron_scheduler.add_job(
            chat_id=chat_id,
            cron_expr=cron_expr,
            prompt=prompt,
            work_dir=work_dir,
            model=settings.runtime_model,
        )
        reply_text = (
            f"✅ <b>Jadwal Tugas Berhasil Dibuat!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 ID: <code>{job['id']}</code>\n"
            f"⏰ Pola Cron: <code>{html.escape(job['cron'])}</code>\n"
            f"📝 Prompt: <i>{html.escape(job['prompt'])}</i>\n"
            f"📁 WORK_DIR: <code>{html.escape(job['work_dir'])}</code>\n"
            f"🤖 Model: <code>{html.escape(job['model'])}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🚀 Jalankan Sekarang", callback_data=f"job:run:{job['id']}"),
                InlineKeyboardButton("⏸️ Jeda Jadwal", callback_data=f"job:tog:{job['id']}"),
            ],
            [
                InlineKeyboardButton("📋 Kelola Semua Jadwal", callback_data="job:list"),
                InlineKeyboardButton("🗑️ Hapus Jadwal", callback_data=f"job:del:{job['id']}"),
            ]
        ])
        if update.message:
            await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception as e:
        if update.message:
            await update.message.reply_text(f"❌ <b>Gagal membuat jadwal:</b> {html.escape(str(e))}", parse_mode=ParseMode.HTML)


async def jobs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /jobs command to list and manage scheduled cron jobs."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    from ...scheduler.manager import cron_scheduler
    jobs = cron_scheduler.list_jobs(chat_id)
    text = cron_scheduler.format_jobs_html(jobs, chat_id=chat_id)
    kb = cron_scheduler.build_jobs_keyboard(jobs, chat_id=chat_id)
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def unschedule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /unschedule <job_id> command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    args = context.args or []
    if not args:
        if update.message:
            await update.message.reply_text(
                "⚠️ Gunakan: <code>/unschedule <job_id></code>\n"
                "Contoh: <code>/unschedule job_1a2b3c</code>\n\n"
                "<i>Ketik <code>/jobs</code> untuk melihat daftar ID tugas aktif.</i>",
                parse_mode=ParseMode.HTML,
            )
        return

    job_id = args[0].strip()
    from ...scheduler.manager import cron_scheduler
    ok = cron_scheduler.remove_job(job_id, chat_id=chat_id)
    if ok:
        if update.message:
            await update.message.reply_text(f"🗑️ <b>Tugas terjadwal <code>{html.escape(job_id)}</code> berhasil dihapus.</b>", parse_mode=ParseMode.HTML)
    else:
        if update.message:
            await update.message.reply_text(f"❌ <b>Tugas <code>{html.escape(job_id)}</code> tidak ditemukan</b> atau bukan milik chat ini.", parse_mode=ParseMode.HTML)

