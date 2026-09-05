"""Preview callbacks (pw:) — extracted from callbacks.py"""
import html
import io
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.constants import ParseMode


async def handle(query, context, chat_id: int, work_dir: str, payload: str) -> bool:
    from ....engine.playwright_preview import playwright_preview
    from ....engine.file_explorer import state_cache
    parts = payload.split(":")
    action = parts[0]
    token = parts[1] if len(parts) > 1 else ""
    target = state_cache.get_path(token) or token or "3000"
    preset = parts[2] if len(parts) > 2 else "desktop"

    if action in ("vw", "rf"):
        await query.answer(f"📸 Memuat snapshot ({preset})...")
        ok, img_bytes, meta = await playwright_preview.capture_url(url_or_port=target, viewport_type=preset)
        if not ok or not img_bytes:
            await query.answer(f"Gagal snapshot: {meta.get('error')}", show_alert=True)
            return True
        url = meta.get("url", target)
        render_time = meta.get("render_time_ms", 0)
        status_code = meta.get("status", 200)
        v_name = meta.get("viewport_name", preset)
        caption = (
            f"📸 <b>Web Preview:</b> <code>{html.escape(url)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 Status: <code>{status_code}</code> • ⏱️ Render: <code>{render_time}ms</code>\n"
            f"📐 Viewport: <b>{v_name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        other_preset = "mobile" if preset == "desktop" else "desktop"
        other_label = "📱 Mobile (390px)" if preset == "desktop" else "💻 Desktop (1440p)"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(other_label, callback_data=f"pw:vw:{token}:{other_preset}"), InlineKeyboardButton("🔄 Refresh", callback_data=f"pw:rf:{token}:{preset}")],
            [InlineKeyboardButton("📜 Console Logs", callback_data=f"pw:log:{token}"), InlineKeyboardButton("📥 Unduh HD", callback_data=f"pw:hd:{token}:{preset}")],
            [InlineKeyboardButton("🗑️ Tutup", callback_data="act:close")]
        ])
        try:
            await query.edit_message_media(media=InputMediaPhoto(media=io.BytesIO(img_bytes), caption=caption, parse_mode=ParseMode.HTML), reply_markup=kb)
        except Exception:
            await context.bot.send_photo(chat_id=chat_id, photo=io.BytesIO(img_bytes), caption=caption, parse_mode=ParseMode.HTML, reply_markup=kb)
        return True

    if action == "log":
        await query.answer("📜 Membaca log konsol browser...")
        valid_url = f"http://localhost:{target}" if target.isdigit() else target
        logs = playwright_preview.get_console_logs(valid_url)
        if not logs:
            logs_text = "✨ <i>Tidak ada pesan log/error di konsol browser.</i>"
        else:
            formatted = "\n".join(logs[-25:])
            logs_text = f"📜 <b>Console Logs ({len(logs)} pesan):</b>\n<blockquote expandable><pre><code>{html.escape(formatted)}</code></pre></blockquote>"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Tutup Log", callback_data="act:close")]])
        await context.bot.send_message(chat_id=chat_id, text=logs_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return True

    if action == "hd":
        await query.answer("📥 Mengirim gambar resolusi HD...")
        ok, img_bytes, meta = await playwright_preview.capture_url(url_or_port=target, viewport_type=preset)
        if ok and img_bytes:
            filename = f"preview_{preset}_{int(time.time())}.jpg"
            await context.bot.send_document(chat_id=chat_id, document=io.BytesIO(img_bytes), filename=filename, caption=f"📸 <b>Snapshot HD ({preset}):</b> <code>{html.escape(meta.get('url', target))}</code>", parse_mode=ParseMode.HTML)
        else:
            await query.answer("Gagal mengambil gambar HD.", show_alert=True)
        return True

    return False
