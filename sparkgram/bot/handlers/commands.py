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
from ...core.git_manager import GitManager
from ...core.macro_manager import macro_manager
from ...engine.file_explorer import file_explorer, state_cache
from ...engine.playwright_preview import playwright_preview, VIEWPORT_PRESETS
from ...engine.port_manager import port_manager
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
        f"✨ <b>SparkGram AI Developer Bridge</b> • <code>{html.escape(settings.runtime_model)}</code>\n\n"
        f"WORK_DIR: <code>{html.escape(current_workdir)}</code>\n"
        f"Session aktif: {active_str}\n"
        f"Mode: <code>{mode}</code> {'('+html.escape(settings.webhook_url)+')' if settings.webhook_url else '(dev, laptop harus nyala)'}\n\n"
        f"<b>🌿 Git Cockpit:</b>\n"
        f"/git - panel status git interaktif (staged, unstaged, branch, 1-tap push)\n"
        f"/diff [staged] - ringkasan diff kode yang dimodifikasi\n"
        f"/commit [pesan] - commit perubahan staged ke git\n"
        f"/push [remote] - push branch ke remote repo\n\n"
        f"<b>🎛️ Developer Recipes & Macros:</b>\n"
        f"/macro - buka Recipe Hub interaktif\n"
        f"/review - review security & logic pada git diff staged\n"
        f"/testgen [file] - otomatis buat unit test pytest\n"
        f"/explain [file] - analisis alur data & tracing modul\n"
        f"/refactor [file] - clean code & optimize modul\n\n"
        f"<b>📁 File Explorer & Artifacts:</b>\n"
        f"/files [subpath] - jelajahi folder proyek via inline button\n"
        f"/tree - lihat struktur file dan folder\n"
        f"/cat [file] - baca cuplikan file kode\n"
        f"/download [file|dir] - unduh file atau arsip .zip bersih\n\n"
        f"<b>📸 UI Preview & Ports:</b>\n"
        f"/preview [port|url] - foto live screenshot web di localhost\n"
        f"/ports - lihat & matikan dev server port lokal (3000, 5173, dll)\n"
        f"/killport [port] - bunuh proses yang menduduki port tertentu\n\n"
        f"<b>🤖 Sesi & Model:</b>\n"
        f"/model [list|1-7] - pilih model AI 1-tap (Spark, Groq, DeepSeek, Claude, dll)\n"
        f"/sessions [n] [kata] - list session (tap nomor untuk switch)\n"
        f"/switch [n|ses_xxx] - ganti session aktif\n"
        f"/workdir [path|list] - ganti/lihat project directory\n"
        f"/new - session baru (reset konteks)\n"
        f"/health /status /export /logs /cancel /restart"
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


# -------------------------------------------------------------
# Git Cockpit & Diff Commands
# -------------------------------------------------------------
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
