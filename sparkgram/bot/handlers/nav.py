"""
Nav & Workdir Handlers — extracted from commands.py (Hari-1 Opsi B).
Handles /nav, /workdir, /pwd and fuzzy Desktop resolution.
"""
import html
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ...config import settings
from ...core.session_manager import session_manager
from ...engine.file_explorer import file_explorer, state_cache
from ..middlewares import is_allowed


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
    low = target.lower()
    if low == "default":
        session_manager.set_chat_workdir(chat_id, settings.work_dir)
        if update.message:
            await update.message.reply_text(f"✅ WORK_DIR di-reset ke default:\n<code>{html.escape(settings.work_dir)}</code>", parse_mode=ParseMode.HTML)
        return
    if low == "list":
        all_wd = getattr(session_manager, "chat_workdirs", {})
        if not all_wd:
            text = "📁 <b>WORK_DIR Mapping:</b>\n<i>Belum ada custom workdir — semua chat pakai default.</i>\n\n<code>" + html.escape(settings.work_dir) + "</code> (default)"
        else:
            lines = [f"• <code>{cid}</code> → <code>{html.escape(wd)}</code>" for cid, wd in all_wd.items()]
            body = "\n".join(lines[:20])
            text = f"📁 <b>WORK_DIR Mapping ({len(all_wd)} chat):</b>\n{body}"
            if len(all_wd) > 20:
                text += f"\n<i>...dan {len(all_wd)-20} lagi</i>"
        cur = session_manager.get_chat_workdir(chat_id)
        text += f"\n\n<b>Chat ini:</b> <code>{html.escape(cur)}</code>"
        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return

    from ...utils.path_resolver import resolve_workdir_path
    current_wd = session_manager.get_chat_workdir(chat_id)
    resolved, dbg = resolve_workdir_path(target, current_workdir=current_wd)

    if resolved is None:
        suggestion = ""
        try:
            desktop = Path.home() / "Desktop"
            if desktop.exists():
                if "hyperspectral" in low or "hyperspec" in low:
                    correct = desktop / "RISET" / "Digitalisasi Karbon" / "HyperSpectral"
                    if correct.exists():
                        suggestion = f"\n\n💡 <b>Saran:</b> Mungkin maksudmu:\n<code>/workdir {html.escape(str(correct))}</code>\natau <code>/workdir desktop/riset/digitalisasi karbon/hyperspectral</code>"
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

    if not resolved.is_dir():
        if update.message:
            await update.message.reply_text(f"❌ Path bukan direktori: <code>{html.escape(str(resolved))}</code>", parse_mode=ParseMode.HTML)
        return

    session_manager.set_chat_workdir(chat_id, str(resolved))
    try:
        tree_text, tree_kb = file_explorer.build_file_tree_ui(base_dir=str(resolved), current_subpath="", page=0)
        header = f"✅ <b>WORK_DIR chat ini diganti ke:</b>\n<code>{html.escape(str(resolved))}</code>"
        if update.message:
            await update.message.reply_text(header, parse_mode=ParseMode.HTML)
            await update.message.reply_text(tree_text, parse_mode=ParseMode.HTML, reply_markup=tree_kb)
        return
    except Exception:
        if update.message:
            await update.message.reply_text(f"✅ WORK_DIR chat ini diganti ke:\n<code>{html.escape(str(resolved))}</code>", parse_mode=ParseMode.HTML)
        return


async def nav_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unified Nav: /nav [pwd|ls|tree|cat|dl|cd <path>|..|-|<fuzzy>] — cd .. mundur, cd maju via fuzzy Desktop."""
    if not is_allowed(update):
        return
    chat_id = update.effective_chat.id if update.effective_chat else 0
    args = context.args or []
    raw = " ".join(args).strip()
    from ...utils.path_resolver import resolve_workdir_path

    current_wd = session_manager.get_chat_workdir(chat_id)

    if not raw:
        text, kb = file_explorer.build_file_tree_ui(base_dir=current_wd, current_subpath="", page=0)
        header = f"📁 <b>NAV</b> • WORK_DIR: <code>{html.escape(current_wd)}</code>\n<i>Subcmd: <code>pwd</code> <code>ls [path]</code> <code>cd &lt;path&gt;</code> <code>cd ..</code> <code>cd -</code> <code>cat &lt;file&gt;</code> <code>dl &lt;path&gt;</code></i>"
        if update.message:
            await update.message.reply_text(header, parse_mode=ParseMode.HTML)
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    low = raw.lower()
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

    if low.startswith("ls") or low.startswith("tree") or low.startswith("dir ") or low == "list":
        sub = raw[2:].strip() if low.startswith("ls") else raw[4:].strip() if low.startswith("tree") else raw[3:].strip() if low.startswith("dir") else raw[4:].strip()
        target_sub = sub.strip().lstrip("/\\")
        text, kb = file_explorer.build_file_tree_ui(base_dir=current_wd, current_subpath=target_sub, page=0)
        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if low.startswith("cat ") or low.startswith("show ") or low.startswith("read "):
        rel = raw.split(" ", 1)[1].strip().lstrip("/\\") if " " in raw else ""
        if not rel:
            if update.message:
                await update.message.reply_text("Gunakan: <code>/nav cat &lt;file&gt;</code>", parse_mode=ParseMode.HTML)
            return
        ok, content = file_explorer.read_file_preview(base_dir=current_wd, rel_path=rel)
        token = state_cache.register_path(rel)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📥 Unduh", callback_data=f"fe:dl:{token}")]]) if ok else None
        if update.message:
            await update.message.reply_text(content, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

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
        if low not in ("help", "h", "?"):
            cd_target = raw
            is_cd_explicit = False

    if cd_target is not None:
        if cd_target in ("..", "../", "up", "back"):
            parent = str(Path(current_wd).parent)
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
        resolved, dbg = resolve_workdir_path(cd_target, current_workdir=current_wd)
        if resolved is None:
            try:
                cand = (Path(current_wd) / cd_target).resolve()
                if cand.exists() and cand.is_dir():
                    resolved = cand
                    dbg = f"cwd+{cd_target}"
            except Exception:
                pass
        if resolved is None:
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

    if update.message:
        await update.message.reply_text(
            f"❓ <b>NAV subcommand tidak dikenal:</b> <code>{html.escape(raw)}</code>\n"
            f"Gunakan: <code>/nav</code> <code>/nav pwd</code> <code>/nav ls [path]</code> <code>/nav cd &lt;path&gt;</code> <code>/nav cd ..</code> <code>/nav cd -</code> <code>/nav cat &lt;file&gt;</code> <code>/nav dl &lt;path&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        text, kb = file_explorer.build_file_tree_ui(base_dir=current_wd, current_subpath="", page=0)
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
