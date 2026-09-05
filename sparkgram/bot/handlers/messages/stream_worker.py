"""Stream worker — extracted from messages.py for 10/10 modularity."""
import time
import html
import asyncio
import logging
from pathlib import Path
from typing import Optional, List

from telegram.constants import ParseMode
from telegram.error import BadRequest, RetryAfter

from ....config import settings
from ....core.session_manager import session_manager
from ....formatters.markdown_html import split_markdown_into_html_chunks
from ....formatters.html_balancer import HTMLTagBalancer
from ....adapters.opencode_adapter import OpenCodeAdapter
from ....engine.process_tree import process_supervisor
from ....memory.manager import memory_manager
from ....ratelimit.token_bucket import rate_limiter
from ....ratelimit.circuit_breaker import telegram_circuit
from .utils import get_short_model_name, get_short_dir, get_current_time_str, build_response_keyboard, build_processing_keyboard

log = logging.getLogger(__name__)


async def stream_execution_worker(
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
                    await bot.edit_message_text(chat_id=chat_id, message_id=status_msg_id, text=text, parse_mode=ParseMode.HTML, reply_markup=build_processing_keyboard())
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
        if (now - last_edit_time) >= settings.rate_limit_sec:
            async with edit_lock:
                frame_idx = (frame_idx + 1) % len(spinner_frames)
                icon = spinner_frames[frame_idx]
                elapsed = now - start_time
                header = f"{icon} <b>Sedang Menulis Respon...</b> • <code>{html.escape(model_short)}</code> • <i>({elapsed:.1f}s)</i>"
                raw_text = "\n".join(accumulated_lines[-25:])
                chunks = split_markdown_into_html_chunks(raw_text, header_html=header, max_chars=3800)
                if not chunks:
                    return
                if not await telegram_circuit.can_execute():
                    log.warning("Circuit OPEN — streaming edit skipped")
                    return
                await rate_limiter.acquire(chat_id)
                try:
                    await bot.edit_message_text(chat_id=chat_id, message_id=status_msg_id, text=chunks[0], parse_mode=ParseMode.HTML, reply_markup=build_processing_keyboard())
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
                                await bot.edit_message_text(chat_id=chat_id, message_id=status_msg_id, text=plain[:3800], reply_markup=build_processing_keyboard())
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

    enriched_prompt = prompt
    try:
        recent = memory_manager.recent(days=3, limit=5)
        if recent:
            mem_ctx = "\n".join(recent)[:800]
            enriched_prompt = f"[MEMORY CONTEXT — recent facts]\n{mem_ctx}\n\n[USER PROMPT]\n{prompt}"
    except Exception as e:
        log.debug(f"memory inject skip: {e}")

    try:
        result = await OpenCodeAdapter.run_prompt_streaming(prompt=enriched_prompt, work_dir=work_dir, model=model, session_id=session_id, files=files, timeout_sec=600.0, on_chunk=on_chunk, on_proc_started=on_proc_started)
        stop_heartbeat.set()
        if not heartbeat_task.done():
            heartbeat_task.cancel()
        final_raw = result.output or (result.error or "Tidak ada output.")
        short_dir = get_short_dir(work_dir)
        time_stamp = get_current_time_str()
        header = f"✅ <b>Selesai (Completed)</b> • <code>{html.escape(model_short)}</code> • <i>({result.duration_sec:.1f}s)</i>\n━━━━━━━━━━━━━━━━━━━━"
        footer = f"\n━━━━━━━━━━━━━━━━━━━━\n📁 <code>{html.escape(short_dir)}</code> • 🕒 <code>{time_stamp}</code>"
        full_content = f"{final_raw}\n{footer}"
        chunks = split_markdown_into_html_chunks(full_content, header_html=header, max_chars=3800)
        kb = build_response_keyboard()
        async with edit_lock:
            if chunks:
                edit_success = False
                for attempt in range(3):
                    await rate_limiter.acquire(chat_id)
                    try:
                        await bot.edit_message_text(chat_id=chat_id, message_id=status_msg_id, text=chunks[0], parse_mode=ParseMode.HTML, reply_markup=kb)
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
                            await bot.edit_message_text(chat_id=chat_id, message_id=status_msg_id, text=plain[:3800], reply_markup=kb)
                            edit_success = True
                            break
                        except Exception:
                            pass
                    except Exception as e:
                        log.debug(f"Completion edit attempt {attempt+1} error: {e}")
                        await asyncio.sleep(0.5)
                if not edit_success:
                    try:
                        await bot.send_message(chat_id=chat_id, text=chunks[0], parse_mode=ParseMode.HTML, reply_markup=kb)
                    except Exception:
                        plain = HTMLTagBalancer.strip_html_tags(chunks[0])
                        await bot.send_message(chat_id=chat_id, text=plain[:3800], reply_markup=kb)
        for remaining_chunk in chunks[1:]:
            try:
                await bot.send_message(chat_id=chat_id, text=remaining_chunk, parse_mode=ParseMode.HTML)
            except Exception:
                plain = HTMLTagBalancer.strip_html_tags(remaining_chunk)
                await bot.send_message(chat_id=chat_id, text=plain[:3800])
    except asyncio.CancelledError:
        stop_heartbeat.set()
        if not heartbeat_task.done():
            heartbeat_task.cancel()
        try:
            async with edit_lock:
                await rate_limiter.acquire(chat_id)
                await bot.edit_message_text(chat_id=chat_id, message_id=status_msg_id, text="🛑 <b>Job Dibatalkan oleh Pengguna.</b>\n<i>Subproses telah dimatikan secara bersih.</i>", parse_mode=ParseMode.HTML, reply_markup=build_response_keyboard())
        except Exception:
            pass
    except Exception as e:
        stop_heartbeat.set()
        if not heartbeat_task.done():
            heartbeat_task.cancel()
        log.error(f"Execution worker failed: {e}")
        try:
            escaped_err = html.escape(str(e))
            err_msg = f"❌ <b>Terjadi Kesalahan Eksekusi</b>\n<blockquote expandable>\n{escaped_err}\n</blockquote>\n\n💡 <i>Tip: Gunakan <code>/model</code> untuk switch model atau <code>/sessions</code> untuk reset sesi.</i>"
            async with edit_lock:
                await rate_limiter.acquire(chat_id)
                await bot.edit_message_text(chat_id=chat_id, message_id=status_msg_id, text=err_msg, parse_mode=ParseMode.HTML, reply_markup=build_response_keyboard())
        except Exception:
            pass
    finally:
        stop_heartbeat.set()
        if not heartbeat_task.done():
            heartbeat_task.cancel()
        proc = session_manager.active_procs.get(chat_id)
        if proc is not None and getattr(proc, "returncode", None) is None:
            try:
                await process_supervisor.kill_process_tree(proc, timeout=2.0)
            except Exception as e:
                log.debug(f"Zombie kill skip: {e}")
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


# Backcompat alias
_stream_execution_worker = stream_execution_worker
