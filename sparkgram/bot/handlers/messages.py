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
from ...engine.process_tree import process_supervisor
from ...memory.manager import memory_manager
from ...ratelimit.token_bucket import rate_limiter
from ...ratelimit.circuit_breaker import telegram_circuit
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
        return str(path_str)[:80]


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


async def execute_prompt_task(
    bot,
    chat_id: int,
    prompt: str,
    message_to_reply=None,
    files: Optional[List[str]] = None,
) -> bool:
    """Dispatches prompt execution to streaming worker with active task tracking."""
    if chat_id in session_manager.active_tasks and not session_manager.active_tasks[chat_id].done():
        warning_text = (
            "⚠️ <b>Ada proses coding yang sedang berjalan di chat ini.</b>\n"
            "Gunakan <code>/cancel</code> atau tap tombol Batalkan jika ingin menghentikannya."
        )
        if message_to_reply:
            await message_to_reply.reply_text(warning_text, parse_mode=ParseMode.HTML)
        else:
            await bot.send_message(chat_id=chat_id, text=warning_text, parse_mode=ParseMode.HTML)
        return False

    work_dir = session_manager.get_chat_workdir(chat_id)
    session_id = session_manager.get_active_session(chat_id)
    model = settings.runtime_model
    model_short = get_short_model_name(model)

    initial_header = (
        f"⚡ <b>Sedang Menghubungkan ke OpenCode Engine...</b> • <code>{html.escape(model_short)}</code>\n"
        f"<i>Koneksi ke local runtime aktif...</i>"
    )
    if message_to_reply:
        status_msg = await message_to_reply.reply_text(
            initial_header,
            parse_mode=ParseMode.HTML,
            reply_markup=build_processing_keyboard(),
        )
    else:
        status_msg = await bot.send_message(
            chat_id=chat_id,
            text=initial_header,
            parse_mode=ParseMode.HTML,
            reply_markup=build_processing_keyboard(),
        )

    task = asyncio.create_task(
        _stream_execution_worker(
            bot=bot,
            chat_id=chat_id,
            status_msg_id=status_msg.message_id,
            prompt=prompt,
            work_dir=work_dir,
            session_id=session_id,
            model=model,
            files=files,
        )
    )
    session_manager.active_tasks[chat_id] = task
    session_manager.task_start_times[chat_id] = time.monotonic()
    return True


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

    # --- Natural language WORK_DIR intent interception (anti-hallucination) ---
    # Catches "pindah ke ...", "ganti direktori ke ...", "cd ..." before AI
    try:
        from ...utils.path_resolver import extract_workdir_target, resolve_workdir_path
        target_candidate = extract_workdir_target(prompt)
        if target_candidate:
            current_wd = session_manager.get_chat_workdir(chat_id)
            resolved, dbg = resolve_workdir_path(target_candidate, current_workdir=current_wd)
            if resolved:
                session_manager.set_chat_workdir(chat_id, str(resolved))
                # Invalidate file explorer cache token for fresh view
                header = (
                    f"✅ <b>WORK_DIR diganti via chat natural language</b>\n"
                    f"<code>{html.escape(str(resolved))}</code>\n"
                    f"<i>Prompt:</i> <code>{html.escape(prompt[:100])}</code>"
                )
                await msg.reply_text(header, parse_mode=ParseMode.HTML)
                # Show file tree preview so user instantly sees result
                from ...engine.file_explorer import file_explorer
                try:
                    tree_text, tree_kb = file_explorer.build_file_tree_ui(
                        base_dir=str(resolved), current_subpath="", page=0
                    )
                    await msg.reply_text(tree_text, parse_mode=ParseMode.HTML, reply_markup=tree_kb)
                except Exception:
                    pass
                log.info(f"Natural workdir switch chat={chat_id} -> {resolved} via '{prompt[:60]}'")
                return
            else:
                # Intent detected but path not found: give helpful error and do NOT forward to AI (avoid hallucination)
                desktop_hint = Path.home() / "Desktop" / "RISET" / "Digitalisasi Karbon" / "HyperSpectral"
                hint_str = ""
                if desktop_hint.exists():
                    hint_str = f"\n\n💡 <b>Saran:</b> <code>/workdir {html.escape(str(desktop_hint))}</code>\natau <code>/workdir desktop/riset/digitalisasi karbon/hyperspectral</code>"
                await msg.reply_text(
                    f"❌ <b>Gagal pindah direktori</b>\nTarget: <code>{html.escape(target_candidate)}</code>\n"
                    f"<i>{html.escape((dbg or '')[:400])}</i>{hint_str}\n\n"
                    f"Coba: <code>/workdir C:\\Path\\Lengkap</code> atau <code>/files</code> untuk jelajahi.",
                    parse_mode=ParseMode.HTML,
                )
                log.warning(f"Natural workdir miss chat={chat_id} target={target_candidate!r} dbg={dbg}")
                return
    except Exception as e:
        log.debug(f"workdir intercept error: {e}")

    await execute_prompt_task(
        bot=context.bot,
        chat_id=chat_id,
        prompt=prompt,
        message_to_reply=msg,
        files=None,
    )


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
        nonlocal frame_idx, last_edit_time
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
                    if not await telegram_circuit.can_execute():
                        log.warning("Circuit OPEN — heartbeat skip")
                        continue
                    await rate_limiter.acquire(chat_id)
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg_id,
                        text=text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=build_processing_keyboard(),
                    )
                    await telegram_circuit.record_success()
                    last_edit_time = time.monotonic()
                except RetryAfter as e:
                    await telegram_circuit.record_failure(retry_after=float(e.retry_after))
                    await asyncio.sleep(e.retry_after + 0.5)
                except Exception as e:
                    await telegram_circuit.record_failure()
                    log.debug(f"Heartbeat edit error: {e}")

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

                # Acquire rate limiter + circuit breaker
                if not await telegram_circuit.can_execute():
                    log.warning("Circuit OPEN — streaming edit skipped")
                    return
                await rate_limiter.acquire(chat_id)
                try:
                    await bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg_id,
                        text=chunks[0],
                        parse_mode=ParseMode.HTML,
                        reply_markup=build_processing_keyboard(),
                    )
                    await telegram_circuit.record_success()
                    last_edit_time = time.monotonic()
                except RetryAfter as e:
                    await telegram_circuit.record_failure(retry_after=float(e.retry_after))
                    await asyncio.sleep(e.retry_after + 0.5)
                except BadRequest as e:
                    if "message is not modified" not in str(e).lower():
                        try:
                            plain = HTMLTagBalancer.strip_html_tags(chunks[0])
                            if await telegram_circuit.can_execute():
                                await rate_limiter.acquire(chat_id)
                                await bot.edit_message_text(
                                    chat_id=chat_id,
                                    message_id=status_msg_id,
                                    text=plain[:3800],
                                    reply_markup=build_processing_keyboard(),
                                )
                                await telegram_circuit.record_success()
                        except RetryAfter as re:
                            await telegram_circuit.record_failure(retry_after=float(re.retry_after))
                        except Exception:
                            await telegram_circuit.record_failure()
                    else:
                        await telegram_circuit.record_success()
                except Exception as e:
                    await telegram_circuit.record_failure()
                    log.debug(f"Streaming edit error: {e}")

    # Fase1: inject recent memory (Hermes parity, max 800 chars) into prompt
    enriched_prompt = prompt
    try:
        recent = memory_manager.recent(days=3, limit=5)
        if recent:
            mem_ctx = "\n".join(recent)[:800]
            enriched_prompt = f"[MEMORY CONTEXT — recent facts]\n{mem_ctx}\n\n[USER PROMPT]\n{prompt}"
    except Exception as e:
        log.debug(f"memory inject skip: {e}")

    try:
        result = await OpenCodeAdapter.run_prompt_streaming(
            prompt=enriched_prompt,
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

        # Edit first chunk with retry and lock protection
        async with edit_lock:
            if chunks:
                edit_success = False
                for attempt in range(3):
                    await rate_limiter.acquire(chat_id)
                    try:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=status_msg_id,
                            text=chunks[0],
                            parse_mode=ParseMode.HTML,
                            reply_markup=kb,
                        )
                        edit_success = True
                        break
                    except RetryAfter as e:
                        await asyncio.sleep(e.retry_after + 0.1)
                    except BadRequest as e:
                        if "message is not modified" in str(e).lower():
                            edit_success = True
                            break
                        try:
                            plain = HTMLTagBalancer.strip_html_tags(chunks[0])
                            await bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=status_msg_id,
                                text=plain[:3800],
                                reply_markup=kb,
                            )
                            edit_success = True
                            break
                        except Exception:
                            pass
                    except Exception as e:
                        log.debug(f"Completion edit attempt {attempt+1} error: {e}")
                        await asyncio.sleep(0.5)

                if not edit_success:
                    try:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=chunks[0],
                            parse_mode=ParseMode.HTML,
                            reply_markup=kb,
                        )
                    except Exception:
                        plain = HTMLTagBalancer.strip_html_tags(chunks[0])
                        await bot.send_message(
                            chat_id=chat_id,
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
            async with edit_lock:
                await rate_limiter.acquire(chat_id)
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
            async with edit_lock:
                await rate_limiter.acquire(chat_id)
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
        # Opt4: ensure zombie opencode proc is killed (tree)
        proc = session_manager.active_procs.get(chat_id)
        if proc is not None and getattr(proc, "returncode", None) is None:
            try:
                await process_supervisor.kill_process_tree(proc, timeout=2.0)
            except Exception as e:
                log.debug(f"Zombie kill skip: {e}")
        # Fase1: persist memory (auto, inspectable markdown)
        try:
            if 'result' in locals() and result and result.success:
                summary = f"{prompt[:120]} -> {str(result.output or '')[:180]}"
                memory_manager.add(summary, chat_id=chat_id, tag="task_success")
            elif 'result' in locals() and result and not result.success:
                memory_manager.add(f"{prompt[:120]} -> ERROR: {str(result.error or '')[:150]}", chat_id=chat_id, tag="task_error")
        except Exception as e:
            log.debug(f"memory persist skip: {e}")
        session_manager.active_procs.pop(chat_id, None)
        session_manager.active_tasks.pop(chat_id, None)
        session_manager.task_start_times.pop(chat_id, None)
