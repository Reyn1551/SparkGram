"""
Natural Text Message and Streaming Execution Handler for SparkGram.
Optimized for exceptional mobile and desktop readability with live heartbeat progress.
"""
import time
import html
import asyncio
import logging
import datetime
from pathlib import Path
from typing import Optional, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import TelegramError, BadRequest, RetryAfter
from telegram.ext import ContextTypes

from ...config import settings
from ...core.session_manager import session_manager
from ...formatters.markdown_html import split_markdown_into_html_chunks, md_to_telegram_html
from ...formatters.html_balancer import HTMLTagBalancer
from ...adapters.opencode_adapter import OpenCodeAdapter
from ...ratelimit.token_bucket import rate_limiter
from ..middlewares import is_allowed

log = logging.getLogger(__name__)


def get_short_model_name(model_str: str) -> str:
    """Extracts clean display name for AI models."""
    if not model_str:
        return "AI"
    if "/" in model_str:
        return model_str.split("/")[-1]
    return model_str


def get_short_dir(path_str: str) -> str:
    """Returns compact directory path for display on mobile screens."""
    try:
        p = Path(path_str).resolve()
        parts = p.parts
        if len(parts) > 2:
            return f".../{parts[-2]}/{parts[-1]}"
        return str(p)
    except Exception:
        return str(path_str)


def get_current_time_str() -> str:
    """Returns current timestamp string for completion stamp."""
    try:
        return datetime.datetime.now().strftime("%H:%M:%S")
    except Exception:
        return ""


def build_response_keyboard() -> InlineKeyboardMarkup:
    """Builds standard interactive action keyboard at bottom of completed AI response."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🆕 Sesi Baru", callback_data="sw:new"),
            InlineKeyboardButton("📁 Switch Sesi", callback_data="sw:refresh"),
        ],
        [
            InlineKeyboardButton("🤖 Ganti Model", callback_data="hlth:model"),
            InlineKeyboardButton("🏥 Health Telemetri", callback_data="hlth:refresh"),
        ]
    ])


def build_processing_keyboard() -> InlineKeyboardMarkup:
    """Builds action keyboard shown while prompt is actively executing."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛑 Batalkan Job", callback_data="act:cancel"),
            InlineKeyboardButton("📜 Cek Log", callback_data="hlth:logs"),
        ]
    ])


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes incoming text prompts and streams results to Telegram."""
    if not is_allowed(update):
        if update.message and update.effective_user:
            await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return

    msg = update.effective_message
    if not msg or not msg.text:
        return

    chat_id = update.effective_chat.id if update.effective_chat else 0
    prompt = msg.text.strip()
    if not prompt:
        return

    # Check if a task is already active for this chat
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
    model_short = get_short_model_name(model)

    # Initial status message with cancel button
    initial_header = (
        f"⚡ <b>Sedang Menghubungkan ke OpenCode Engine...</b> • <code>{html.escape(model_short)}</code>\n"
        f"<i>Koneksi ke local runtime aktif...</i>"
    )
    status_msg = await msg.reply_text(initial_header, parse_mode=ParseMode.HTML, reply_markup=build_processing_keyboard())

    # Launch streaming execution worker as an asyncio Task
    task = asyncio.create_task(
        _stream_execution_worker(
            bot=context.bot,
            chat_id=chat_id,
            status_msg_id=status_msg.message_id,
            prompt=prompt,
            work_dir=work_dir,
            session_id=session_id,
            model=model,
            files=None,
        )
    )
    session_manager.active_tasks[chat_id] = task


async def _stream_execution_worker(
    bot,
    chat_id: int,
    status_msg_id: int,
    prompt: str,
    work_dir: str,
    session_id: Optional[str],
    model: str,
    files: Optional[List[str]] = None,
):
    """Internal streaming worker with throttled updates and live heartbeat progress."""
    accumulated_lines: List[str] = []
    start_time = time.monotonic()
    last_edit_time = 0.0
    edit_lock = asyncio.Lock()
    spinner_frames = ["⚡", "🔍", "✏️", "⚙️", "✨"]
    frame_idx = 0
    model_short = get_short_model_name(model)
    has_received_output = False
    stop_heartbeat = asyncio.Event()

    async def heartbeat_loop():
        """Updates progress ticker and stage every 1.5s when waiting for initial tokens."""
        nonlocal frame_idx
        while not stop_heartbeat.is_set():
            await asyncio.sleep(1.5)
            if stop_heartbeat.is_set() or has_received_output:
                break
            now = time.monotonic()
            elapsed = now - start_time
            frame_idx = (frame_idx + 1) % len(spinner_frames)
            icon = spinner_frames[frame_idx]

            if elapsed < 4.0:
                stage = "⚡ Menghubungkan ke runtime engine & loading model..."
            elif elapsed < 9.0:
                stage = "🧠 AI sedang menganalisis prompt & konteks repository..."
            elif elapsed < 16.0:
                stage = "⚙️ Sedang memproses reasoning & token generation..."
            else:
                stage = "⌛ Masih memproses di provider LLM (antrean server)..."

            header = f"{icon} <b>Sedang Berpikir & Memproses...</b> • <code>{html.escape(model_short)}</code> • <i>({elapsed:.1f}s)</i>"
            text = f"{header}\n<blockquote expandable>\n{stage}\n</blockquote>"

            async with edit_lock:
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=build_processing_keyboard(),
                    )
                except Exception:
                    pass

    heartbeat_task = asyncio.create_task(heartbeat_loop())

    async def on_proc_started(proc):
        session_manager.active_procs[chat_id] = proc

    async def on_chunk(chunk: str):
        nonlocal last_edit_time, frame_idx, has_received_output
        has_received_output = True
        accumulated_lines.append(chunk)
        now = time.monotonic()

        # Throttle edits to safe rate (>= 1.2s)
        if (now - last_edit_time) >= settings.rate_limit_sec:
            async with edit_lock:
                frame_idx = (frame_idx + 1) % len(spinner_frames)
                icon = spinner_frames[frame_idx]
                elapsed = now - start_time
                header = f"{icon} <b>Sedang Menulis Respon...</b> • <code>{html.escape(model_short)}</code> • <i>({elapsed:.1f}s)</i>"
                
                # Show last 25 lines of output in live box
                raw_text = "\n".join(accumulated_lines[-25:])
                chunks = split_markdown_into_html_chunks(raw_text, header_html=header, max_chars=3800)
                if not chunks:
                    return

                # Acquire rate limiter tokens
                await rate_limiter.acquire(chat_id)
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg_id,
                        text=chunks[0],
                        parse_mode=ParseMode.HTML,
                        reply_markup=build_processing_keyboard(),
                    )
                    last_edit_time = time.monotonic()
                except RetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                except BadRequest as e:
                    if "message is not modified" not in str(e).lower():
                        try:
                            plain = HTMLTagBalancer.strip_html_tags(chunks[0])
                            await bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=status_msg_id,
                                text=plain[:3800],
                                reply_markup=build_processing_keyboard(),
                            )
                        except Exception:
                            pass
                except Exception as e:
                    log.debug(f"Streaming edit error: {e}")

    try:
        result = await OpenCodeAdapter.run_prompt_streaming(
            prompt=prompt,
            work_dir=work_dir,
            model=model,
            session_id=session_id,
            files=files,
            timeout_sec=600.0,
            on_chunk=on_chunk,
            on_proc_started=on_proc_started,
        )

        stop_heartbeat.set()
        if not heartbeat_task.done():
            heartbeat_task.cancel()

        final_raw = result.output or (result.error or "Tidak ada output.")
        short_dir = get_short_dir(work_dir)
        time_stamp = get_current_time_str()
        
        # Crystal clear completion badge
        header = (
            f"✅ <b>Selesai (Completed)</b> • <code>{html.escape(model_short)}</code> • <i>({result.duration_sec:.1f}s)</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        footer = f"\n━━━━━━━━━━━━━━━━━━━━\n📁 <code>{html.escape(short_dir)}</code> • 🕒 <code>{time_stamp}</code>"
        
        full_content = f"{final_raw}\n{footer}"
        chunks = split_markdown_into_html_chunks(full_content, header_html=header, max_chars=3800)

        kb = build_response_keyboard()

        # Edit first chunk
        if chunks:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    text=chunks[0],
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                )
            except Exception:
                plain = HTMLTagBalancer.strip_html_tags(chunks[0])
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    text=plain[:3800],
                    reply_markup=kb,
                )

        # Send remaining chunks if response is multi-page
        for remaining_chunk in chunks[1:]:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=remaining_chunk,
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                plain = HTMLTagBalancer.strip_html_tags(remaining_chunk)
                await bot.send_message(
                    chat_id=chat_id,
                    text=plain[:3800],
                )

    except asyncio.CancelledError:
        stop_heartbeat.set()
        if not heartbeat_task.done():
            heartbeat_task.cancel()
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg_id,
                text="🛑 <b>Job Dibatalkan oleh Pengguna.</b>\n<i>Subproses telah dimatikan secara bersih.</i>",
                parse_mode=ParseMode.HTML,
                reply_markup=build_response_keyboard(),
            )
        except Exception:
            pass

    except Exception as e:
        stop_heartbeat.set()
        if not heartbeat_task.done():
            heartbeat_task.cancel()
        log.error(f"Execution worker failed: {e}")
        try:
            escaped_err = html.escape(str(e))
            err_msg = (
                f"❌ <b>Terjadi Kesalahan Eksekusi</b>\n"
                f"<blockquote expandable>\n{escaped_err}\n</blockquote>\n\n"
                f"💡 <i>Tip: Gunakan <code>/model</code> untuk switch model atau <code>/sessions</code> untuk reset sesi.</i>"
            )
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg_id,
                text=err_msg,
                parse_mode=ParseMode.HTML,
                reply_markup=build_response_keyboard(),
            )
        except Exception:
            pass

    finally:
        stop_heartbeat.set()
        if not heartbeat_task.done():
            heartbeat_task.cancel()
        session_manager.active_procs.pop(chat_id, None)
        session_manager.active_tasks.pop(chat_id, None)
