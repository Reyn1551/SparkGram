"""File explorer callbacks (fe:) — extracted from callbacks.py"""
import html
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode


async def handle(query, context, chat_id: int, work_dir: str, payload: str) -> bool:
    from ....engine.file_explorer import file_explorer, state_cache
    parts = payload.split(":")
    action = parts[0]
    token = parts[1] if len(parts) > 1 else ""

    if action == "noop":
        await query.answer()
        return True

    rel_path = state_cache.get_path(token) or ""

    if action == "cd":
        await query.answer("📁 Beralih folder...")
        text, kb = file_explorer.build_file_tree_ui(base_dir=work_dir, current_subpath=rel_path, page=0)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if action == "rf":
        await query.answer("🔄 Memperbarui direktori...")
        text, kb = file_explorer.build_file_tree_ui(base_dir=work_dir, current_subpath=rel_path, page=0)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if action == "p":
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        await query.answer()
        text, kb = file_explorer.build_file_tree_ui(base_dir=work_dir, current_subpath=rel_path, page=page)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if action == "vw":
        await query.answer("📄 Membaca file...")
        ok, content = file_explorer.read_file_preview(base_dir=work_dir, rel_path=rel_path)
        parent_rel = str(Path(rel_path).parent).replace("\\", "/") if "/" in rel_path else "."
        parent_token = state_cache.register_path(parent_rel)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Unduh File", callback_data=f"fe:dl:{token}")],
            [InlineKeyboardButton("◀ Kembali ke Folder", callback_data=f"fe:cd:{parent_token}")]
        ])
        try:
            await query.edit_message_text(content, parse_mode=ParseMode.HTML, reply_markup=kb if ok else None)
        except Exception:
            pass
        return True

    if action == "dl":
        await query.answer("📥 Mengunduh file...")
        try:
            target = file_explorer.safe_resolve(work_dir, rel_path)
            if target.is_file():
                await context.bot.send_document(chat_id=chat_id, document=open(target, "rb"), filename=target.name, caption=f"📄 <code>{html.escape(target.name)}</code>", parse_mode=ParseMode.HTML)
        except Exception as e:
            await query.answer(f"Gagal mengunduh: {e}", show_alert=True)
        return True

    if action == "zip":
        await query.answer("📦 Mengompresi folder zip...")
        ok, zip_bytes, zip_name = file_explorer.create_safe_zip(base_dir=work_dir, rel_path=rel_path)
        if ok and zip_bytes:
            import io
            await context.bot.send_document(chat_id=chat_id, document=io.BytesIO(zip_bytes), filename=zip_name, caption=f"📦 Arsip Zip: <code>{html.escape(zip_name)}</code>", parse_mode=ParseMode.HTML)
        else:
            await query.answer(f"Gagal membuat zip: {zip_name}", show_alert=True)
        return True

    return False
