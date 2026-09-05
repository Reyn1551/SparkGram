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

# === Modular split Hari-2 ===
from .sys import sys_hub_cmd, health_cmd, sysinfo_cmd, logs_cmd, preview_cmd, ports_cmd, killport_cmd
from .jobs import jobs_hub_cmd, schedule_cmd, jobs_cmd, unschedule_cmd
from .git import git_hub_cmd, build_git_cockpit_ui, git_cmd, diff_cmd, commit_cmd, push_cmd
from .recipe import recipe_hub_cmd, build_macro_hub_ui, macro_cmd, review_cmd, testgen_cmd, explain_cmd, refactor_cmd


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
        f"✨ <b>SparkGram Ultra — 8 Core</b> • <code>{html.escape(settings.runtime_model)}</code>\n\n"
        f"WORK_DIR: <code>{html.escape(current_workdir)}</code>\n"
        f"Session aktif: {active_str}\n"
        f"Mode: <code>{mode}</code> {'('+html.escape(settings.webhook_url)+')' if settings.webhook_url else '(dev)'}\n\n"
        f"<b>📁 NAV — File Explorer & WorkDir (cd .. mendukung)</b>\n"
        f"<code>/nav</code> — explorer WORK_DIR (inline buttons) — File Explorer\n"
        f"<code>/nav pwd</code> — lihat workdir\n"
        f"<code>/nav ls [path]</code> — list folder\n"
        f"<code>/nav cd &lt;path&gt;</code> — ganti workdir (fuzzy: <code>desktop/riset/.../hyperspectral</code>)\n"
        f"<code>/nav cd ..</code> <code>/nav cd -</code> — mundur/maju (history)\n"
        f"<code>/nav cat &lt;file&gt;</code> <code>/nav dl &lt;path&gt;</code>\n\n"
        f"<b>💬 SESSION — Sesi</b>\n"
        f"<code>/session</code> — list sesi workdir ini\n"
        f"<code>/session switch 1</code> <code>/session new</code> <code>/session rename Judul</code> <code>/session delete id</code> <code>/session export</code>\n\n"
        f"<b>🌿 Git Cockpit:</b>\n"
        f"<code>/git</code> — panel status interaktif (staged, unstaged, branch)\n"
        f"<code>/git diff</code> <code>/git commit</code> <code>/git push</code>\n\n"
        f"<b>🎛️ Developer Recipes & Macro Hub:</b>\n"
        f"<code>/recipe</code> — hub interaktif\n"
        f"<code>/recipe review</code> <code>/recipe testgen &lt;file&gt;</code> <code>/recipe explain</code> <code>/recipe refactor</code>\n\n"
        f"<b>🏥 SYS — System</b>\n"
        f"<code>/sys health</code> — CPU/RAM/Disk/GPU/Baterai\n"
        f"<code>/sys logs [n]</code> <code>/sys ports</code> <code>/sys killport 3000</code> <code>/sys preview 3000</code>\n\n"
        f"<b>⏰ JOBS — Scheduler</b>\n"
        f"<code>/jobs</code> — list cron\n"
        f"<code>/jobs add 0 9 * * * prompt</code> <code>/jobs rm job_xxx</code> <code>/jobs run job_xxx</code>\n\n"
        f"<b>🧠 MODEL & MEMORY</b>\n"
        f"<code>/model</code> — 1-tap ganti model\n"
        f"<code>/memory [query]</code> — search memory\n\n"
        f"<i>Aliases lama hidden: /workdir→/nav cd, /files→/nav, /pwd→/nav pwd, /sessions→/session, /health→/sys health, /macro→/recipe, /schedule→/jobs add</i>\n"
        f"/help /id /cancel /restart"
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


# ----------------------------------------------------------------
# ULTRA: Unified NAV handler — menggantikan workdir+files+tree+pwd+cat+download
# ----------------------------------------------------------------
# ULTRA: Unified SESSION hub — menggantikan sessions+switch+new+rename+delete+export+status
# ----------------------------------------------------------------
# ULTRA: Unified SYS hub — menggantikan health+sysinfo+logs+ports+killport+preview+status
# ----------------------------------------------------------------
# ULTRA: Unified JOBS hub — menggantikan schedule+jobs+unschedule
# ----------------------------------------------------------------
# ULTRA: Unified GIT hub — /git [status|diff|commit|push] (hapus shortcuts)
# ----------------------------------------------------------------
# ULTRA: Unified RECIPE hub — /recipe [list|review|testgen|explain|refactor]
async def memory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /memory [search] — persistent memory viewer (Hermes parity)."""
    if not is_allowed(update):
        return
    from ...memory.manager import memory_manager
    args = context.args or []
    q = " ".join(args).strip()
    if q:
        hits = memory_manager.search(q, limit=15)
        if not hits:
            text = f"🔍 <b>Memory search:</b> <code>{html.escape(q)}</code>\n<i>Tidak ada hasil.</i>"
        else:
            lines = [f"{h['day']} | {html.escape(h['line'][:200])}" for h in hits]
            inner = "\n".join(lines)
            text = f"🔍 <b>Memory search:</b> <code>{html.escape(q)}</code> — {len(hits)} hit(s)\n<blockquote expandable>\n{inner}\n</blockquote>"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🧠 Lihat Recent", callback_data="mem:recent")]])
    else:
        recent = memory_manager.recent(days=7, limit=20)
        stats = memory_manager.stats()
        if not recent:
            text = f"🧠 <b>Persistent Memory</b> — {stats['files']} file(s), {stats['lines']} baris\n<i>Belum ada memory. Memory otomatis terisi setiap task sukses.</i>"
        else:
            inner = "\n".join(html.escape(l) for l in recent)
            text = f"🧠 <b>Persistent Memory</b> — {stats['files']} file(s), {stats['lines']} baris\n<blockquote expandable>\n{inner}\n</blockquote>"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Search Mode", callback_data="mem:search")],
            [InlineKeyboardButton("🗑️ Cleanup >30d", callback_data="mem:cleanup")],
        ])
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


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


# -------------------------------------------------------------
# Git Cockpit & Diff Commands
# -------------------------------------------------------------
async def files_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /files and /tree commands."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    work_dir = session_manager.get_chat_workdir(chat_id)
    args = context.args or []
    subpath = args[0] if args else ""

    text, kb = file_explorer.build_file_tree_ui(base_dir=work_dir, current_subpath=subpath, page=0)
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def cat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /cat <filepath> command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    work_dir = session_manager.get_chat_workdir(chat_id)
    args = context.args or []
    if not args:
        if update.message:
            await update.message.reply_text("⚠️ Gunakan: <code>/cat <nama_file></code>", parse_mode=ParseMode.HTML)
        return

    rel_path = args[0]
    ok, content = file_explorer.read_file_preview(base_dir=work_dir, rel_path=rel_path)
    if update.message:
        token = state_cache.register_path(rel_path)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📥 Unduh File Utuh", callback_data=f"fe:dl:{token}")]])
        await update.message.reply_text(content, parse_mode=ParseMode.HTML, reply_markup=kb if ok else None)


async def download_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /download <filepath|dirpath> command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    work_dir = session_manager.get_chat_workdir(chat_id)
    args = context.args or []
    target_str = args[0] if args else ""

    try:
        target = file_explorer.safe_resolve(work_dir, target_str)
    except Exception as e:
        if update.message:
            await update.message.reply_text(f"❌ {e}", parse_mode=ParseMode.HTML)
        return

    if target.is_file():
        if update.message:
            await update.message.reply_document(
                document=open(target, "rb"),
                filename=target.name,
                caption=f"📄 <code>{html.escape(target.name)}</code>",
                parse_mode=ParseMode.HTML,
            )
    else:
        ok, zip_bytes, zip_name = file_explorer.create_safe_zip(base_dir=work_dir, rel_path=target_str)
        if ok and zip_bytes:
            if update.message:
                import io
                await update.message.reply_document(
                    document=io.BytesIO(zip_bytes),
                    filename=zip_name,
                    caption=f"📦 Arsip Zip: <code>{html.escape(zip_name)}</code>",
                    parse_mode=ParseMode.HTML,
                )
        else:
            if update.message:
                await update.message.reply_text(f"❌ Gagal membuat zip: {zip_name}", parse_mode=ParseMode.HTML)


# -------------------------------------------------------------
# Visual UI Preview & Ports Management
# -------------------------------------------------------------