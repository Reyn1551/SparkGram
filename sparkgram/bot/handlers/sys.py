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
SYS Handlers — extracted from commands.py (Hari-2 Opsi B).
"""

# ----------------------------------------------------------------
async def sys_hub_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified SYS: /sys [health|logs|ports|preview|status]"""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    args = context.args or []
    sub = (args[0].lower() if args else "health")
    rest = args[1:] if len(args) > 1 else []

    if sub in ("health", "sysinfo", "info", ""):
        # Call health logic inline
        from ...utils.system_monitor import get_system_health, format_health_html, build_health_keyboard
        active_session = session_manager.get_active_session(chat_id)
        is_busy = chat_id in session_manager.active_tasks and not session_manager.active_tasks[chat_id].done()
        data = get_system_health()
        text = format_health_html(data, active_session=active_session, is_busy=is_busy)
        kb = build_health_keyboard()
        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return
    if sub in ("logs", "log"):
        n = int(rest[0]) if rest and rest[0].isdigit() else 25
        n = max(5, min(100, n))
        from ...utils.log_masker import mask_sensitive_text
        log_file = settings.log_file
        if not log_file.exists():
            if update.message:
                await update.message.reply_text("<i>Belum ada log.</i>", parse_mode=ParseMode.HTML)
            return
        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                tail = f.readlines()[-n:]
            masked = mask_sensitive_text("".join(tail))
            esc = html.escape(masked[-3500:])
            if update.message:
                await update.message.reply_text(f"📜 <b>Logs ({len(tail)}):</b>\n<pre><code>{esc}</code></pre>", parse_mode=ParseMode.HTML)
        except Exception as e:
            if update.message:
                await update.message.reply_text(f"❌ Gagal baca log: {html.escape(str(e))}", parse_mode=ParseMode.HTML)
        return
    if sub in ("ports", "port", "ps"):
        from ...engine.port_manager import port_manager
        text, kb = port_manager.build_ports_ui()
        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return
    if sub in ("killport", "kill"):
        if not rest or not rest[0].isdigit():
            if update.message:
                await update.message.reply_text("Gunakan: <code>/sys killport 3000</code>", parse_mode=ParseMode.HTML)
            return
        from ...engine.port_manager import port_manager
        port_num = int(rest[0])
        ok, msg, _ = port_manager.kill_port(port_num)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔌 Ports", callback_data="port:list")]])
        if update.message:
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=kb)
        return
    if sub in ("preview", "snap", "shot", "web"):
        # reuse preview logic
        target = rest[0] if rest else None
        if not target:
            from ...engine.playwright_preview import playwright_preview
            detected = playwright_preview.detect_active_dev_port()
            target = str(detected) if detected else "3000"
        if update.message:
            wait_msg = await update.message.reply_text(f"📸 Snapshot <code>{html.escape(str(target))}</code>...", parse_mode=ParseMode.HTML)
        else:
            wait_msg = None
        from ...engine.playwright_preview import playwright_preview
        from ...engine.file_explorer import state_cache as _sc
        ok, img_bytes, meta = await playwright_preview.capture_url(url_or_port=target, viewport_type="desktop")
        if not ok or not img_bytes:
            err = meta.get("error", "gagal")
            if wait_msg:
                await wait_msg.edit_text(f"❌ Preview gagal: {html.escape(err)}", parse_mode=ParseMode.HTML)
            return
        url = meta.get("url", target)
        render_time = meta.get("render_time_ms", 0)
        status_code = meta.get("status", 200)
        v_name = meta.get("viewport_name", "Desktop")
        token = _sc.register_path(str(target))
        caption = f"📸 <b>Web Preview:</b> <code>{html.escape(url)}</code>\n🌐 {status_code} • ⏱️ {render_time}ms • 📐 {v_name}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 Mobile", callback_data=f"pw:vw:{token}:mobile"), InlineKeyboardButton("💻 Desktop", callback_data=f"pw:vw:{token}:desktop")],
            [InlineKeyboardButton("🔄 Refresh", callback_data=f"pw:rf:{token}:desktop"), InlineKeyboardButton("📜 Logs", callback_data=f"pw:log:{token}")],
        ])
        import io as _io
        if wait_msg:
            try:
                await wait_msg.delete()
            except Exception:
                pass
        if update.message:
            await update.message.reply_photo(photo=_io.BytesIO(img_bytes), caption=caption, parse_mode=ParseMode.HTML, reply_markup=kb)
        return
    if sub in ("status", "stat"):
        work_dir = session_manager.get_chat_workdir(chat_id)
        active = session_manager.get_active_session(chat_id)
        is_running = chat_id in session_manager.active_tasks and not session_manager.active_tasks[chat_id].done()
        task_label = "🏃 Sibuk" if is_running else "🟢 Idle"
        from ...utils.system_monitor import get_system_health
        data = get_system_health()
        # compact status
        text = (
            f"📊 <b>SYS Status</b>\n"
            f"• Task: {task_label}\n"
            f"• Session: <code>{html.escape(active or '-')}</code>\n"
            f"• WORK_DIR: <code>{html.escape(work_dir)}</code>\n"
            f"• Model: <code>{html.escape(settings.runtime_model)}</code>\n"
            f"• CPU: {data.get('cpu', {}).get('percent', '?')}%\n"
            f"• RAM: {data.get('memory', {}).get('percent', '?')}%"
        )
        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return
    if update.message:
        await update.message.reply_text("Gunakan: <code>/sys [health|logs|ports|killport|preview|status]</code>", parse_mode=ParseMode.HTML)


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


async def preview_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /preview [port|url] and /snap commands."""
    if not is_allowed(update):
        return
    args = context.args or []
    target = args[0] if args else None

    if not target:
        detected_port = playwright_preview.detect_active_dev_port()
        if detected_port:
            target = str(detected_port)
        else:
            target = "3000"

    wait_msg = None
    if update.message:
        wait_msg = await update.message.reply_text(
            f"📸 <i>Mengambil snapshot UI live untuk <code>{html.escape(str(target))}</code>...</i>",
            parse_mode=ParseMode.HTML,
        )

    ok, img_bytes, meta = await playwright_preview.capture_url(
        url_or_port=target,
        viewport_type="desktop",
    )

    if not ok or not img_bytes:
        err_msg = meta.get("error", "Gagal mengambil snapshot.")
        if wait_msg:
            await wait_msg.edit_text(
                f"❌ <b>Gagal Preview UI:</b> {html.escape(err_msg)}\n\n"
                f"<i>Tips: Pastikan server lokal kamu sedang berjalan (misal: <code>http://localhost:{target}</code>).</i>",
                parse_mode=ParseMode.HTML,
            )
        return

    url = meta.get("url", target)
    render_time = meta.get("render_time_ms", 0)
    status_code = meta.get("status", 200)
    v_name = meta.get("viewport_name", "Desktop")
    token = state_cache.register_path(target)

    caption = (
        f"📸 <b>Web Preview:</b> <code>{html.escape(url)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 Status: <code>{status_code}</code> • ⏱️ Render: <code>{render_time}ms</code>\n"
        f"📐 Viewport: <b>{v_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📱 Mobile (390px)", callback_data=f"pw:vw:{token}:mobile"),
            InlineKeyboardButton("💻 Desktop (1440p)", callback_data=f"pw:vw:{token}:desktop"),
        ],
        [
            InlineKeyboardButton("🔄 Refresh Snapshot", callback_data=f"pw:rf:{token}:desktop"),
            InlineKeyboardButton("📜 Console Logs", callback_data=f"pw:log:{token}"),
        ],
        [InlineKeyboardButton("📥 Unduh Gambar HD", callback_data=f"pw:hd:{token}:desktop")]
    ])

    if wait_msg:
        try:
            await wait_msg.delete()
        except Exception:
            pass

    import io
    if update.message:
        await update.message.reply_photo(
            photo=io.BytesIO(img_bytes),
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )


async def ports_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /ports command to list active TCP listening ports."""
    if not is_allowed(update):
        return
    text, kb = port_manager.build_ports_ui()
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def killport_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /killport <port> command."""
    if not is_allowed(update):
        return
    args = context.args or []
    if not args or not args[0].isdigit():
        if update.message:
            await update.message.reply_text("⚠️ Gunakan: <code>/killport <nomor_port></code> (contoh: <code>/killport 3000</code>)", parse_mode=ParseMode.HTML)
        return

    port_num = int(args[0])
    ok, msg, _ = port_manager.kill_port(port_num)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔌 Buka Panel Ports", callback_data="port:list")]])
    if update.message:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=kb)


# -------------------------------------------------------------
# Cron Task Scheduler Handlers
# -------------------------------------------------------------