"""
Health / SysInfo / Logs handlers — Companion PC monitoring.
"""
import html
import time
import logging
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ...config import settings
from ...system.health import get_health_snapshot, format_health_html, format_sysinfo_html
from ..middlewares import is_allowed

log = logging.getLogger(__name__)


def _health_keyboard(detailed: bool = False) -> InlineKeyboardMarkup:
    if detailed:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="hl:refresh_detail"),
             InlineKeyboardButton("🩺 Ringkas", callback_data="hl:refresh")],
            [InlineKeyboardButton("📋 Logs", callback_data="hl:logs"),
             InlineKeyboardButton("❌ Tutup", callback_data="hl:close")],
        ])
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="hl:refresh"),
         InlineKeyboardButton("🔍 Detail", callback_data="hl:refresh_detail")],
        [InlineKeyboardButton("📋 Logs (50)", callback_data="hl:logs"),
         InlineKeyboardButton("🖥️ SysInfo", callback_data="hl:sysinfo")],
    ])


async def health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update) or not update.message:
        if update.effective_user and update.message:
            await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    snap = get_health_snapshot()
    text = format_health_html(snap, detailed=False)
    kb = _health_keyboard(detailed=False)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def sysinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update) or not update.message:
        return
    snap = get_health_snapshot()
    text = format_sysinfo_html(snap)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="hl:sysinfo_refresh"),
         InlineKeyboardButton("🩺 Health", callback_data="hl:refresh")],
        [InlineKeyboardButton("❌ Tutup", callback_data="hl:close")],
    ])
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update) or not update.message:
        return
    args = context.args or []
    try:
        n = int(args[0]) if args else 50
    except ValueError:
        n = 50
    n = max(1, min(n, 200))

    log_file = settings.log_file
    if not log_file.exists():
        await update.message.reply_text(f"📋 <b>Logs</b>: file belum ada (<code>{html.escape(str(log_file))}</code>)", parse_mode=ParseMode.HTML)
        return

    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-n:]
        body = "\n".join(tail) if tail else "(kosong)"
        # mask sensitive? just escape html
        body_esc = html.escape(body[-3500:])  # keep within telegram limit
        text = f"📋 <b>Logs terakhir {len(tail)} baris</b> — <code>{html.escape(str(log_file))}</code>\n<pre>{body_esc}</pre>"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh Logs", callback_data="hl:logs"),
             InlineKeyboardButton("🩺 Health", callback_data="hl:refresh")],
        ])
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal baca log: <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)


async def health_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline buttons hl:*"""
    query = update.callback_query
    if not query:
        return
    if not is_allowed(update):
        await query.answer("Akses ditolak.", show_alert=True)
        return
    data = query.data or ""
    if not data.startswith("hl:"):
        return

    action = data[3:]

    if action == "close":
        try:
            await query.message.delete()
        except Exception:
            await query.answer("Ditutup")
        return

    if action in ("refresh", "refresh_detail"):
        detailed = action == "refresh_detail"
        snap = get_health_snapshot()
        text = format_health_html(snap, detailed=detailed) if not detailed or action == "refresh_detail" and False else format_health_html(snap, detailed=detailed)
        # For detail view we show health detailed? keep health html with detailed flag
        kb = _health_keyboard(detailed=detailed)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception as e:
            # fallback plain
            if "message is not modified" not in str(e).lower():
                log.debug(f"health edit fail: {e}")
        await query.answer("✅ Refreshed")
        return

    if action == "sysinfo" or action == "sysinfo_refresh":
        snap = get_health_snapshot()
        text = format_sysinfo_html(snap)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="hl:sysinfo_refresh"),
             InlineKeyboardButton("🩺 Health", callback_data="hl:refresh")],
            [InlineKeyboardButton("❌ Tutup", callback_data="hl:close")],
        ])
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        await query.answer("✅ SysInfo refreshed")
        return

    if action == "logs":
        log_file = settings.log_file
        n = 50
        if not log_file.exists():
            await query.answer("Log file belum ada", show_alert=True)
            return
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = lines[-n:]
            body = "\n".join(tail) if tail else "(kosong)"
            body_esc = html.escape(body[-3500:])
            text = f"📋 <b>Logs terakhir {len(tail)} baris</b>\n<pre>{body_esc}</pre>"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh Logs", callback_data="hl:logs"),
                 InlineKeyboardButton("🩺 Health", callback_data="hl:refresh")],
            ])
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception as e:
            await query.answer(f"Error: {e}", show_alert=True)
        else:
            await query.answer("✅ Logs refreshed")
        return

    await query.answer()
