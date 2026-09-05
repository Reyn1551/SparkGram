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
GIT Handlers — extracted from commands.py (Hari-2 Opsi B).
"""

# ----------------------------------------------------------------
async def git_hub_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified GIT: /git [status|diff|commit|push] — wrapper ke git cockpit"""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    work_dir = session_manager.get_chat_workdir(chat_id)
    args = context.args or []
    sub = (args[0].lower() if args else "status")
    # status
    if sub in ("status", "st", "show", ""):
        text, kb = await build_git_cockpit_ui(work_dir)
        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return
    if sub in ("diff", "d"):
        staged = len(args) > 1 and args[1].lower() == "staged"
        from ...core.git_manager import GitManager
        gm = GitManager(work_dir)
        ok, diff_text, stats = await gm.get_diff(staged_only=staged)
        if not ok or not diff_text:
            if update.message:
                await update.message.reply_text("✨ Tidak ada diff.", parse_mode=ParseMode.HTML)
            return
        mode_label = "Staged" if staged else "All"
        header = f"📝 <b>Git Diff ({mode_label})</b> +{stats['added']} -{stats['deleted']} 📁{stats['files_count']}\n"
        body = f"<blockquote expandable><pre><code>{html.escape(diff_text[:3200])}</code></pre></blockquote>"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🌿 Git", callback_data="git:status")]])
        if update.message:
            await update.message.reply_text(header + body, parse_mode=ParseMode.HTML, reply_markup=kb)
        return
    if sub in ("commit", "ci"):
        msg = " ".join(args[1:]).strip()
        from ...core.git_manager import GitManager
        gm = GitManager(work_dir)
        status = await gm.get_status_summary()
        if not status.get("staged"):
            if update.message:
                await update.message.reply_text("⚠️ Tidak ada staged. /git status → Stage All dulu.", parse_mode=ParseMode.HTML)
            return
        if not msg:
            msg = gm.generate_ai_commit_message(status)
        ok, res = await gm.commit(msg)
        if update.message:
            await update.message.reply_text(res, parse_mode=ParseMode.HTML)
        return
    if sub in ("push", "p"):
        remote = args[1] if len(args) > 1 else "origin"
        branch = args[2] if len(args) > 2 else None
        from ...core.git_manager import GitManager
        gm = GitManager(work_dir)
        if update.message:
            wait_msg = await update.message.reply_text("🚀 Push...", parse_mode=ParseMode.HTML)
        else:
            wait_msg = None
        ok, res = await gm.push(remote=remote, branch=branch)
        if wait_msg:
            await wait_msg.edit_text(res, parse_mode=ParseMode.HTML)
        elif update.message:
            await update.message.reply_text(res, parse_mode=ParseMode.HTML)
        return
    if update.message:
        await update.message.reply_text("Gunakan: <code>/git [status|diff|commit|push]</code>", parse_mode=ParseMode.HTML)


async def build_git_cockpit_ui(work_dir: str):
    """Generates visual Git Cockpit HTML card and interactive control buttons."""
    gm = GitManager(work_dir)
    status = await gm.get_status_summary()
    repo_name = Path(work_dir).name

    if not status.get("is_repo"):
        text = (
            f"🌿 <b>Git Cockpit:</b> <code>{html.escape(repo_name)}</code>\n"
            f"⚠️ <i>Direktori ini bukan repositori Git aktif.</i>\n\n"
            f"Gunakan <code>/workdir</code> untuk berpindah ke folder proyek Git."
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📁 Ganti WORK_DIR", callback_data="sw:workdir")],
            [InlineKeyboardButton("🔄 Cek Ulang", callback_data="git:status")]
        ])
        return text, keyboard

    branch = status.get("branch", "unknown")
    staged = status.get("staged", [])
    unstaged = status.get("unstaged", [])
    untracked = status.get("untracked", [])
    stats = status.get("stats", {"added": 0, "deleted": 0})

    text = (
        f"🌿 <b>Git Cockpit</b> • <code>{html.escape(repo_name)}</code> (<code>{html.escape(branch)}</code>)\n"
        f"📊 <b>Status:</b> {len(staged)} staged, {len(unstaged)} unstaged, {len(untracked)} untracked (<b>+{stats['added']} / -{stats['deleted']}</b>)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )

    if staged:
        text += "<b>Staged Changes:</b>\n"
        for f in staged[:6]:
            text += f"🟢 <code>{html.escape(f)}</code>\n"
        if len(staged) > 6:
            text += f"<i>...dan {len(staged)-6} file lainnya</i>\n"
        text += "\n"

    if unstaged:
        text += "<b>Unstaged Modifications:</b>\n"
        for f in unstaged[:6]:
            text += f"🟡 <code>{html.escape(f)}</code>\n"
        if len(unstaged) > 6:
            text += f"<i>...dan {len(unstaged)-6} file lainnya</i>\n"
        text += "\n"

    if untracked:
        text += "<b>Untracked Files:</b>\n"
        for f in untracked[:4]:
            text += f"⚪ <code>{html.escape(f)}</code>\n"
        if len(untracked) > 4:
            text += f"<i>...dan {len(untracked)-4} file lainnya</i>\n"
        text += "\n"

    if not staged and not unstaged and not untracked:
        text += "✨ <i>Working tree clean (tidak ada perubahan kode).</i>\n"

    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━"

    buttons = [
        [
            InlineKeyboardButton("🔍 Diff Staged", callback_data="git:diff_stg"),
            InlineKeyboardButton("🔍 Diff All", callback_data="git:diff_all"),
        ],
        [
            InlineKeyboardButton("➕ Stage All", callback_data="git:stage_all"),
            InlineKeyboardButton("➖ Unstage All", callback_data="git:unstage_all"),
        ],
        [
            InlineKeyboardButton("✨ AI Commit", callback_data="git:ai_commit"),
            InlineKeyboardButton("🚀 Push Remote", callback_data="git:push"),
        ],
        [
            InlineKeyboardButton("📥 Ekspor .patch", callback_data="git:export_patch"),
            InlineKeyboardButton("🔄 Refresh", callback_data="git:status"),
        ]
    ]
    return text, InlineKeyboardMarkup(buttons)


async def git_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /git command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    work_dir = session_manager.get_chat_workdir(chat_id)
    text, kb = await build_git_cockpit_ui(work_dir)
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def diff_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /diff [staged] command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    work_dir = session_manager.get_chat_workdir(chat_id)
    args = context.args or []
    staged_only = len(args) > 0 and args[0].lower() == "staged"

    gm = GitManager(work_dir)
    ok, diff_text, stats = await gm.get_diff(staged_only=staged_only)

    if not ok:
        if update.message:
            await update.message.reply_text(f"❌ {diff_text}", parse_mode=ParseMode.HTML)
        return

    if not diff_text:
        msg = "✨ <b>Tidak ada perubahan kode yang belum di-commit.</b>"
        if update.message:
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        return

    mode_label = "Staged" if staged_only else "All Working Tree"
    header = (
        f"📝 <b>Git Diff ({mode_label})</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🟢 <b>+{stats['added']}</b> Baris   🔴 <b>-{stats['deleted']}</b> Baris   📁 <b>{stats['files_count']}</b> Berkas\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    if len(diff_text) > 3200:
        truncated = diff_text[:3200] + "\n\n... (diff terpotong — gunakan tombol Ekspor .patch)"
        body = f"<blockquote expandable><pre><code class=\"language-diff\">{html.escape(truncated)}</code></pre></blockquote>"
    else:
        body = f"<blockquote expandable><pre><code class=\"language-diff\">{html.escape(diff_text)}</code></pre></blockquote>"

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Ekspor .patch", callback_data="git:export_patch"),
            InlineKeyboardButton("✨ AI Commit", callback_data="git:ai_commit"),
        ],
        [InlineKeyboardButton("🌿 Kembali ke Git Cockpit", callback_data="git:status")]
    ])
    if update.message:
        await update.message.reply_text(header + body, parse_mode=ParseMode.HTML, reply_markup=kb)


async def commit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /commit <pesan> command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    work_dir = session_manager.get_chat_workdir(chat_id)
    msg_parts = context.args or []
    commit_msg = " ".join(msg_parts).strip()

    gm = GitManager(work_dir)
    status = await gm.get_status_summary()

    if not status.get("staged"):
        if update.message:
            await update.message.reply_text(
                "⚠️ <b>Tidak ada perubahan staged.</b>\n"
                "Gunakan <code>/git</code> lalu tap <b>➕ Stage All</b> terlebih dahulu, atau ketik <code>/commit -a <pesan></code>.",
                parse_mode=ParseMode.HTML,
            )
        return

    if not commit_msg:
        commit_msg = gm.generate_ai_commit_message(status)

    ok, res = await gm.commit(commit_msg)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Push Remote Sekarang", callback_data="git:push")]])
    if update.message:
        if ok:
            await update.message.reply_text(res, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await update.message.reply_text(f"❌ {res}", parse_mode=ParseMode.HTML)


async def push_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /push [remote] [branch] command."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    work_dir = session_manager.get_chat_workdir(chat_id)
    args = context.args or []
    remote = args[0] if len(args) > 0 else "origin"
    branch = args[1] if len(args) > 1 else None

    if update.message:
        wait_msg = await update.message.reply_text("🚀 <b>Sedang melakukan git push ke remote...</b>", parse_mode=ParseMode.HTML)
    else:
        wait_msg = None

    gm = GitManager(work_dir)
    ok, res = await gm.push(remote=remote, branch=branch)

    if wait_msg:
        await wait_msg.edit_text(res, parse_mode=ParseMode.HTML)


# -------------------------------------------------------------
# Developer Macro Hub & Recipes
# -------------------------------------------------------------