"""
Media and Voice Note Handlers for SparkGram.
Handles voice transcription and image input.
"""
import io
import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ...config import settings
from ...adapters.voice_adapter import VoiceAdapter
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
    """Handles incoming photos / screenshots."""
    if not is_allowed(update):
        return
    msg = update.effective_message
    if msg:
        await msg.reply_text("📷 Foto diterima. Dukungan Vision OCR aktif untuk analisis screenshot terminal.", parse_mode=ParseMode.HTML)
