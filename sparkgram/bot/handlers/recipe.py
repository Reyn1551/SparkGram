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
RECIPE Handlers — extracted from commands.py (Hari-2 Opsi B).
"""

# ----------------------------------------------------------------
async def recipe_hub_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified RECIPE: /recipe [review|testgen|explain|refactor|doc]"""
    if not is_allowed(update):
        return
    args = context.args or []
    if not args:
        text, kb = build_macro_hub_ui()
        # rename macro hub title to recipe for consistency
        text = text.replace("Macro", "Recipe")
        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return
    sub = args[0].lower()
    target = " ".join(args[1:]).strip()
    # map review etc.
    if sub in ("review", "testgen", "explain", "refactor", "doc"):
        await _dispatch_macro(update, context, sub, target=target)
        return
    if sub in ("list", "ls"):
        text, kb = build_macro_hub_ui()
        text = text.replace("Macro", "Recipe")
        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return
    # fallback try as macro id
    await _dispatch_macro(update, context, sub, target=target)


def build_macro_hub_ui():
    """Generates interactive Macro Hub menu."""
    recipes = macro_manager.list_recipes()
    text = (
        "🎛️ <b>Developer Recipe & Macro Hub</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Pilih template otomasi cerdas untuk dieksekusi pada repositori aktif:\n\n"
    )
    buttons = []
    for r in recipes:
        text += f"{r['emoji']} <b>/{r['id']}</b> — {r['name']}\n<i>{r['description']}</i>\n\n"
        buttons.append([
            InlineKeyboardButton(f"{r['emoji']} Jalankan /{r['id']}", callback_data=f"macro:run:{r['id']}")
        ])
    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    return text, InlineKeyboardMarkup(buttons)


async def macro_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /macro [resep] command."""
    if not is_allowed(update):
        return
    args = context.args or []
    if args:
        recipe_id = args[0].lower()
        await _dispatch_macro(update, context, recipe_id, " ".join(args[1:]))
        return

    text, kb = build_macro_hub_ui()
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def _dispatch_macro(update: Update, context: ContextTypes.DEFAULT_TYPE, recipe_id: str, target: str = ""):
    """Helper to assemble macro prompt and trigger AI streaming execution."""
    from .messages import execute_prompt_task
    chat_id = update.effective_chat.id if update.effective_chat else 0
    work_dir = session_manager.get_chat_workdir(chat_id)

    ok, prompt, title = await macro_manager.build_macro_prompt(
        recipe_id=recipe_id,
        work_dir=work_dir,
        target=target,
    )
    if not ok:
        # Fix: support both Command (/refactor) and Callback (macro:run:refactor) contexts
        # When triggered via inline button, update.message is None — use bot.send_message
        err_text = prompt
        # Add helper for file-target recipes
        if "memerlukan argumen nama file" in prompt:
            err_text += f"\n\n💡 <i>Tap /files untuk pilih file, lalu kirim:</i> <code>/{recipe_id} sparkgram/config.py</code>"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("📁 Buka File Explorer", callback_data="fe:cd:.")]])
        else:
            kb = None
        try:
            if update.message:
                await update.message.reply_text(err_text, parse_mode=ParseMode.HTML, reply_markup=kb)
            elif update.callback_query:
                await context.bot.send_message(chat_id=chat_id, text=err_text, parse_mode=ParseMode.HTML, reply_markup=kb)
            else:
                await context.bot.send_message(chat_id=chat_id, text=err_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return

    try:
        if update.message:
            await update.message.reply_text(f"🚀 <b>Mengeksekusi Recipe: {title}</b>...", parse_mode=ParseMode.HTML)
        elif update.callback_query:
            await context.bot.send_message(chat_id=chat_id, text=f"🚀 <b>Mengeksekusi Recipe: {title}</b>...", parse_mode=ParseMode.HTML)
    except Exception:
        pass

    await execute_prompt_task(
        bot=context.bot,
        chat_id=chat_id,
        prompt=prompt,
        message_to_reply=update.effective_message,
    )


async def review_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /review shortcut."""
    if not is_allowed(update):
        return
    await _dispatch_macro(update, context, "review")


async def testgen_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /testgen <file> shortcut."""
    if not is_allowed(update):
        return
    args = context.args or []
    target = args[0] if args else ""
    await _dispatch_macro(update, context, "testgen", target=target)


async def explain_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /explain <target> shortcut."""
    if not is_allowed(update):
        return
    args = context.args or []
    target = " ".join(args) if args else ""
    await _dispatch_macro(update, context, "explain", target=target)


async def refactor_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /refactor <target> shortcut."""
    if not is_allowed(update):
        return
    args = context.args or []
    target = " ".join(args) if args else ""
    await _dispatch_macro(update, context, "refactor", target=target)


# -------------------------------------------------------------
# File Explorer & Artifact Delivery
# -------------------------------------------------------------