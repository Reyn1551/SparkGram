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
    """Handles /workdir command with fuzzy Desktop shorthand support."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    args = context.args or []

    if not args:
        current_workdir = session_manager.get_chat_workdir(chat_id)
        active = session_manager.get_active_session(chat_id)
        active_str = f"\nSession: <code>{html.escape(active)}</code>" if active else ""
        # Show preview of target folder contents
        try:
            exists = Path(current_workdir).exists()
            preview = f"\n{'✅ Ada' if exists else '⚠️ Tidak ditemukan di disk'} • <code>{html.escape(str(Path(current_workdir).resolve()))}</code>"
        except Exception:
            preview = ""
        if update.message:
            await update.message.reply_text(
                f"📁 <b>WORK_DIR Chat Ini:</b>\n<code>{html.escape(current_workdir)}</code>{active_str}{preview}\n\n"
                f"Ganti direktori:\n<code>/workdir C:\\Path\\Folder</code>\n"
                f"Shorthand: <code>/workdir desktop/riset/hyperspectral</code>\n"
                f"Reset default: <code>/workdir default</code>\n"
                f"List mapping: <code>/workdir list</code>",
                parse_mode=ParseMode.HTML,
            )
        return

    target = " ".join(args).strip()

    # Handle subcommands: default, list
    low = target.lower()
    if low == "default":
        session_manager.set_chat_workdir(chat_id, settings.work_dir)
        if update.message:
            await update.message.reply_text(f"✅ WORK_DIR di-reset ke default:\n<code>{html.escape(settings.work_dir)}</code>", parse_mode=ParseMode.HTML)
        return
    if low == "list":
        # Show all chat_workdirs mapping
        all_wd = getattr(session_manager, "chat_workdirs", {})
        if not all_wd:
            text = "📁 <b>WORK_DIR Mapping:</b>\n<i>Belum ada custom workdir — semua chat pakai default.</i>\n\n<code>" + html.escape(settings.work_dir) + "</code> (default)"
        else:
            lines = [f"• <code>{cid}</code> → <code>{html.escape(wd)}</code>" for cid, wd in all_wd.items()]
            body = "\n".join(lines[:20])
            text = f"📁 <b>WORK_DIR Mapping ({len(all_wd)} chat):</b>\n{body}"
            if len(all_wd) > 20:
                text += f"\n<i>...dan {len(all_wd)-20} lagi</i>"
        # Also show current chat's dir
        cur = session_manager.get_chat_workdir(chat_id)
        text += f"\n\n<b>Chat ini:</b> <code>{html.escape(cur)}</code>"
        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return

    # Try fuzzy resolver first
    from ...utils.path_resolver import resolve_workdir_path
    current_wd = session_manager.get_chat_workdir(chat_id)
    resolved, dbg = resolve_workdir_path(target, current_workdir=current_wd)

    if resolved is None:
        # Fallback: try raw Path check for accurate error message, then suggest
        p = Path(target)
        # Provide helpful suggestions: list Desktop/RISET if target contains hyperspectral etc.
        suggestion = ""
        try:
            desktop = Path.home() / "Desktop"
            if desktop.exists():
                # If target low contains hyperspectral, suggest correct path
                if "hyperspectral" in low or "hyperspec" in low:
                    correct = desktop / "RISET" / "Digitalisasi Karbon" / "HyperSpectral"
                    if correct.exists():
                        suggestion = f"\n\n💡 <b>Saran:</b> Mungkin maksudmu:\n<code>/workdir {html.escape(str(correct))}</code>\natau <code>/workdir desktop/riset/digitalisasi karbon/hyperspectral</code>"
                # General: list top-level Desktop folders if miss
                if not suggestion:
                    top = [x.name for x in desktop.iterdir() if x.is_dir()][:6]
                    if top:
                        suggestion = f"\n\n💡 <b>Folder di Desktop:</b> <code>{html.escape(', '.join(top))}</code>"
        except Exception:
            pass

        if update.message:
            await update.message.reply_text(
                f"❌ Path tidak ditemukan: <code>{html.escape(target)}</code>\n"
                f"<i>Debug: {html.escape(dbg or 'no match')}</i>{suggestion}\n\n"
                f"Gunakan absolute path atau shorthand:\n<code>/workdir desktop/riset/digitalisasi karbon/hyperspectral</code>",
                parse_mode=ParseMode.HTML,
            )
        return

    # Validate is dir (resolver already ensures is_dir, but double-check)
    if not resolved.is_dir():
        if update.message:
            await update.message.reply_text(f"❌ Path bukan direktori: <code>{html.escape(str(resolved))}</code>", parse_mode=ParseMode.HTML)
        return

    # Success: persist
    session_manager.set_chat_workdir(chat_id, str(resolved))
    # Build success UI with file preview
    from ...engine.file_explorer import file_explorer
    try:
        tree_text, tree_kb = file_explorer.build_file_tree_ui(base_dir=str(resolved), current_subpath="", page=0)
        # tree_text already contains folder listing; we will send it as follow-up
        header = f"✅ <b>WORK_DIR chat ini diganti ke:</b>\n<code>{html.escape(str(resolved))}</code>"
        if update.message:
            await update.message.reply_text(header, parse_mode=ParseMode.HTML)
            # Show file explorer snapshot so user instantly sees hyperspectral contents
            await update.message.reply_text(tree_text, parse_mode=ParseMode.HTML, reply_markup=tree_kb)
        return
    except Exception:
        if update.message:
            await update.message.reply_text(f"✅ WORK_DIR chat ini diganti ke:\n<code>{html.escape(str(resolved))}</code>", parse_mode=ParseMode.HTML)
        return


# ----------------------------------------------------------------
# ULTRA: Unified NAV handler — menggantikan workdir+files+tree+pwd+cat+download
# ----------------------------------------------------------------
async def nav_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified Nav: /nav [pwd|ls|tree|cat|dl|cd <path>|..|-|<fuzzy>] — cd .. mundur, cd maju via fuzzy Desktop."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    args = context.args or []
    raw = " ".join(args).strip()
    from ...engine.file_explorer import file_explorer
    from ...utils.path_resolver import resolve_workdir_path

    current_wd = session_manager.get_chat_workdir(chat_id)

    # Help / no args → explorer at workdir root + pwd banner
    if not raw:
        text, kb = file_explorer.build_file_tree_ui(base_dir=current_wd, current_subpath="", page=0)
        header = f"📁 <b>NAV</b> • WORK_DIR: <code>{html.escape(current_wd)}</code>\n<i>Subcmd: <code>pwd</code> <code>ls [path]</code> <code>cd &lt;path&gt;</code> <code>cd ..</code> <code>cd -</code> <code>cat &lt;file&gt;</code> <code>dl &lt;path&gt;</code></i>"
        if update.message:
            await update.message.reply_text(header, parse_mode=ParseMode.HTML)
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    low = raw.lower()
    # pwd / status
    if low in ("pwd", "status", "info", "where"):
        active = session_manager.get_active_session(chat_id)
        active_str = f"\nSession: <code>{html.escape(active)}</code>" if active else ""
        hist = session_manager.peek_workdir_history(chat_id)
        hist_str = f"\nPrev: <code>{html.escape(hist)}</code> (cd -)" if hist else ""
        if update.message:
            await update.message.reply_text(
                f"📁 <b>WORK_DIR:</b> <code>{html.escape(current_wd)}</code>{active_str}{hist_str}\n"
                f"<i>Base:</i> <code>{html.escape(settings.work_dir)}</code>",
                parse_mode=ParseMode.HTML,
            )
        return

    # ls / tree / dir / list
    if low.startswith("ls") or low.startswith("tree") or low.startswith("dir ") or low == "list":
        # Extract subpath after command
        sub = raw[2:].strip() if low.startswith("ls") else raw[4:].strip() if low.startswith("tree") else raw[3:].strip() if low.startswith("dir") else raw[4:].strip()
        # Handle "ls" alone → root, "ls data" → data subfolder (temporary browse, not cd)
        target_sub = sub.strip().lstrip("/\\")
        text, kb = file_explorer.build_file_tree_ui(base_dir=current_wd, current_subpath=target_sub, page=0)
        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # cat / show / read
    if low.startswith("cat ") or low.startswith("show ") or low.startswith("read "):
        rel = raw.split(" ", 1)[1].strip().lstrip("/\\") if " " in raw else ""
        if not rel:
            if update.message:
                await update.message.reply_text("Gunakan: <code>/nav cat &lt;file&gt;</code>", parse_mode=ParseMode.HTML)
            return
        ok, content = file_explorer.read_file_preview(base_dir=current_wd, rel_path=rel)
        from ...engine.file_explorer import state_cache
        token = state_cache.register_path(rel)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📥 Unduh", callback_data=f"fe:dl:{token}")]]) if ok else None
        if update.message:
            await update.message.reply_text(content, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # dl / download / get / zip
    if low.startswith("dl ") or low.startswith("download ") or low.startswith("get ") or low.startswith("zip "):
        rel = raw.split(" ", 1)[1].strip().lstrip("/\\") if " " in raw else ""
        try:
            target = file_explorer.safe_resolve(current_wd, rel)
        except Exception as e:
            if update.message:
                await update.message.reply_text(f"❌ {html.escape(str(e))}", parse_mode=ParseMode.HTML)
            return
        if target.is_file():
            if update.message:
                await update.message.reply_document(document=open(target, "rb"), filename=target.name, caption=f"📄 <code>{html.escape(target.name)}</code>", parse_mode=ParseMode.HTML)
        else:
            ok, zip_bytes, zip_name = file_explorer.create_safe_zip(base_dir=current_wd, rel_path=rel)
            if ok and zip_bytes:
                import io
                if update.message:
                    await update.message.reply_document(document=io.BytesIO(zip_bytes), filename=zip_name, caption=f"📦 <code>{html.escape(zip_name)}</code>", parse_mode=ParseMode.HTML)
            else:
                if update.message:
                    await update.message.reply_text(f"❌ Gagal zip: {html.escape(zip_name)}", parse_mode=ParseMode.HTML)
        return

    # cd handling (explicit or implicit)
    # Normalize various cd syntaxes
    cd_target = None
    is_cd_explicit = False
    if low.startswith("cd ") or low.startswith("workdir ") or low.startswith("cwd ") or low.startswith("chdir "):
        cd_target = raw.split(" ", 1)[1].strip() if " " in raw else ""
        is_cd_explicit = True
    elif low in ("..", "up", "back", "../", "cd ..", "cd.."):
        cd_target = ".."
        is_cd_explicit = True
    elif low == "-" or low == "cd -" or low == "back -":
        cd_target = "-"
        is_cd_explicit = True
    elif low in ("~", "home", "default"):
        cd_target = "~"
        is_cd_explicit = True
    else:
        # Implicit cd: if raw looks like path, treat as cd
        # Heuristic: contains slash, backslash, desktop, hyperspectral, drive letter, or is single folder name that resolves
        # Avoid treating "help" as cd
        if low not in ("help", "h", "?"):
            cd_target = raw
            # need to ensure we don't misinterpret "ls" etc already handled
            is_cd_explicit = False

    if cd_target is not None:
        # Special handling for cd variants
        if cd_target in ("..", "../", "up", "back"):
            parent = str(Path(current_wd).parent)
            # Ensure parent exists and is dir
            if not Path(parent).exists() or not Path(parent).is_dir():
                if update.message:
                    await update.message.reply_text(f"❌ Parent tidak ditemukan: <code>{html.escape(parent)}</code>", parse_mode=ParseMode.HTML)
                return
            session_manager.set_chat_workdir(chat_id, parent)
            text, kb = file_explorer.build_file_tree_ui(base_dir=parent, current_subpath="", page=0)
            if update.message:
                await update.message.reply_text(f"⬆️ <b>cd ..</b> → <code>{html.escape(parent)}</code>", parse_mode=ParseMode.HTML)
                await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        if cd_target == "-" or cd_target == "cd -":
            prev = session_manager.pop_workdir_history(chat_id)
            if not prev or not Path(prev).exists():
                if update.message:
                    await update.message.reply_text("❌ Tidak ada prev workdir (cd -). History kosong.", parse_mode=ParseMode.HTML)
                return
            session_manager.set_chat_workdir(chat_id, prev)
            text, kb = file_explorer.build_file_tree_ui(base_dir=prev, current_subpath="", page=0)
            if update.message:
                await update.message.reply_text(f"↩️ <b>cd -</b> → <code>{html.escape(prev)}</code>", parse_mode=ParseMode.HTML)
                await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        if cd_target in ("~", "home", "default", "base"):
            default_wd = settings.work_dir
            session_manager.set_chat_workdir(chat_id, default_wd)
            text, kb = file_explorer.build_file_tree_ui(base_dir=default_wd, current_subpath="", page=0)
            if update.message:
                await update.message.reply_text(f"🏠 <b>cd ~</b> → default: <code>{html.escape(default_wd)}</code>", parse_mode=ParseMode.HTML)
                await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        # Normal cd with fuzzy resolver
        resolved, dbg = resolve_workdir_path(cd_target, current_workdir=current_wd)
        # Fallback: try as relative subfolder inside current workdir (for maju)
        if resolved is None:
            try:
                cand = (Path(current_wd) / cd_target).resolve()
                if cand.exists() and cand.is_dir():
                    resolved = cand
                    dbg = f"cwd+{cd_target}"
            except Exception:
                pass
        if resolved is None:
            # Provide helpful error
            if update.message:
                await update.message.reply_text(
                    f"❌ cd gagal: <code>{html.escape(cd_target)}</code>\n<i>{html.escape((dbg or '')[:400])}</i>\n\nCoba <code>/nav ls</code> atau <code>/nav pwd</code>", parse_mode=ParseMode.HTML
                )
            return
        session_manager.set_chat_workdir(chat_id, str(resolved))
        text, kb = file_explorer.build_file_tree_ui(base_dir=str(resolved), current_subpath="", page=0)
        prefix = "📁 <b>cd</b> →" if is_cd_explicit else "📁 <b>WORK_DIR</b> →"
        if update.message:
            await update.message.reply_text(f"{prefix} <code>{html.escape(str(resolved))}</code>", parse_mode=ParseMode.HTML)
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # Fallback: unknown subcommand → show help + explorer
    if update.message:
        await update.message.reply_text(
            f"❓ <b>NAV subcommand tidak dikenal:</b> <code>{html.escape(raw)}</code>\n"
            f"Gunakan: <code>/nav</code> <code>/nav pwd</code> <code>/nav ls [path]</code> <code>/nav cd &lt;path&gt;</code> <code>/nav cd ..</code> <code>/nav cd -</code> <code>/nav cat &lt;file&gt;</code> <code>/nav dl &lt;path&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        text, kb = file_explorer.build_file_tree_ui(base_dir=current_wd, current_subpath="", page=0)
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


# ----------------------------------------------------------------
# ULTRA: Unified SESSION hub — menggantikan sessions+switch+new+rename+delete+export+status
# ----------------------------------------------------------------
async def session_hub_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified SESSION: /session [ls|switch|new|rename|delete|export|status]"""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    args = context.args or []
    sub = (args[0].lower() if args else "ls")
    rest = args[1:] if len(args) > 1 else []

    # ls / list
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
    # switch
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
    # new
    if sub in ("new", "create", "reset"):
        session_manager.set_active_session(chat_id, None)
        if update.message:
            await update.message.reply_text("🆕 Session di-reset. Pesan berikutnya akan buat session baru.", parse_mode=ParseMode.HTML)
        return
    # rename
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
    # delete / rm
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
    # export
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
    # status
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
    # unknown
    if update.message:
        await update.message.reply_text("Gunakan: <code>/session [ls|switch|new|rename|delete|export|status]</code>", parse_mode=ParseMode.HTML)


# ----------------------------------------------------------------
# ULTRA: Unified SYS hub — menggantikan health+sysinfo+logs+ports+killport+preview+status
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


# ----------------------------------------------------------------
# ULTRA: Unified JOBS hub — menggantikan schedule+jobs+unschedule
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


# ----------------------------------------------------------------
# ULTRA: Unified GIT hub — /git [status|diff|commit|push] (hapus shortcuts)
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


# ----------------------------------------------------------------
# ULTRA: Unified RECIPE hub — /recipe [list|review|testgen|explain|refactor]
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


# -------------------------------------------------------------
# Cron Task Scheduler Handlers
# -------------------------------------------------------------
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

