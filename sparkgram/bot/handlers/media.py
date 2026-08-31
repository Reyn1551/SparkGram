"""
Media and Voice Note Handlers for SparkGram.
Handles voice transcription and image/screenshot input with automatic prompt execution.
"""
import io
import os
import html
import asyncio
import logging
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ...config import settings
from ...adapters.voice_adapter import VoiceAdapter
from ...core.session_manager import session_manager
from ..middlewares import is_allowed

log = logging.getLogger(__name__)


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Transcribes incoming Telegram voice note and prompts for execution."""
    if not is_allowed(update):
        return

    msg = update.effective_message
    if not msg or not msg.voice:
        return

    status_msg = await msg.reply_text("🎙️ <i>Mentranskripsi pesan suara via Groq Whisper...</i>", parse_mode=ParseMode.HTML)
    
    try:
        voice_file = await context.bot.get_file(msg.voice.file_id)
        audio_buffer = io.BytesIO()
        await voice_file.download_to_memory(audio_buffer)
        audio_bytes = audio_buffer.getvalue()

        ok, transcript = await VoiceAdapter.transcribe_audio_bytes(audio_bytes, filename="voice.oga")
        if not ok:
            await status_msg.edit_text(f"❌ {html.escape(transcript)}", parse_mode=ParseMode.HTML)
            return

        reply_text = (
            f"🗣️ <b>Transkripsi Suara:</b>\n\n"
            f"<blockquote>{html.escape(transcript)}</blockquote>\n\n"
            f"<i>Kirimkan teks di atas sebagai prompt jika ingin mengeksekusi.</i>"
        )
        await status_msg.edit_text(reply_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        log.error(f"Voice handler error: {e}")
        try:
            await status_msg.edit_text(f"❌ Gagal memproses audio: {html.escape(str(e))}", parse_mode=ParseMode.HTML)
        except Exception:
            pass


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming photos / screenshots and automatically executes attached caption."""
    if not is_allowed(update):
        return

    msg = update.effective_message
    if not msg:
        return

    photos = msg.photo
    doc = msg.document

    if not photos and not doc:
        return

    # Choose highest resolution photo or document image
    file_id = photos[-1].file_id if photos else doc.file_id
    caption = (msg.caption or "").strip()

    images_dir = settings.log_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    img_filename = f"img_{msg.message_id}_{int(os.getpid())}.jpg"
    img_path = images_dir / img_filename

    try:
        tg_file = await context.bot.get_file(file_id)
        await tg_file.download_to_drive(custom_path=img_path)

        if caption:
            # User provided a caption with the image -> automatically run as coding prompt!
            from .messages import _stream_execution_worker, build_processing_keyboard
            chat_id = update.effective_chat.id if update.effective_chat else 0

            if chat_id in session_manager.active_tasks and not session_manager.active_tasks[chat_id].done():
                await msg.reply_text(
                    "⚠️ <b>Ada proses coding yang sedang berjalan di chat ini.</b>\n"
                    "Gunakan <code>/cancel</code> atau tap tombol Batalkan jika ingin menghentikannya.",
                    parse_mode=ParseMode.HTML,
                )
                return

            work_dir = session_manager.get_chat_workdir(chat_id)
            session_id = session_manager.get_active_session(chat_id)
            model = settings.runtime_model

            initial_header = (
                f"📷 <b>Menganalisis Gambar & Prompt...</b> • <code>{html.escape(model)}</code>\n"
                f"<i>File: <code>{html.escape(img_filename)}</code></i>"
            )
            status_msg = await msg.reply_text(initial_header, parse_mode=ParseMode.HTML, reply_markup=build_processing_keyboard())

            task = asyncio.create_task(
                _stream_execution_worker(
                    bot=context.bot,
                    chat_id=chat_id,
                    status_msg_id=status_msg.message_id,
                    prompt=caption,
                    work_dir=work_dir,
                    session_id=session_id,
                    model=model,
                    files=[str(img_path)],
                )
            )
            session_manager.active_tasks[chat_id] = task

        else:
            # No caption provided -> acknowledge image receipt and prompt user
            await msg.reply_text(
                f"📷 <b>Screenshot / Foto Berhasil Diterima</b>\n\n"
                f"File tersimpan di: <code>{html.escape(str(img_path))}</code>\n\n"
                f"<i>Kirim pesan balasan atau teks prompt untuk menganalisis gambar ini.</i>",
                parse_mode=ParseMode.HTML,
            )

    except Exception as e:
        log.error(f"Photo handler error: {e}")
        await msg.reply_text(f"❌ Gagal memproses gambar: {html.escape(str(e))}", parse_mode=ParseMode.HTML)
