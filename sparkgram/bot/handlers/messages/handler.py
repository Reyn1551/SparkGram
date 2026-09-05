"""Message handler — extracted from messages.py for 10/10 modularity."""
import html
import time
import asyncio
from pathlib import Path
from typing import Optional, List

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ....config import settings
from ....core.session_manager import session_manager
from ...middlewares import is_allowed
from .utils import get_short_model_name, build_processing_keyboard
from .stream_worker import stream_execution_worker

import logging
log = logging.getLogger(__name__)


async def execute_prompt_task(bot, chat_id: int, prompt: str, message_to_reply=None, files: Optional[List[str]] = None) -> bool:
    if chat_id in session_manager.active_tasks and not session_manager.active_tasks[chat_id].done():
        warning_text = "⚠️ <b>Ada proses coding yang sedang berjalan di chat ini.</b>\nGunakan <code>/cancel</code> atau tap tombol Batalkan jika ingin menghentikannya."
        if message_to_reply:
            await message_to_reply.reply_text(warning_text, parse_mode=ParseMode.HTML)
        else:
            await bot.send_message(chat_id=chat_id, text=warning_text, parse_mode=ParseMode.HTML)
        return False
    work_dir = session_manager.get_chat_workdir(chat_id)
    session_id = session_manager.get_active_session(chat_id)
    model = settings.runtime_model
    model_short = get_short_model_name(model)
    initial_header = f"⚡ <b>Sedang Menghubungkan ke OpenCode Engine...</b> • <code>{html.escape(model_short)}</code>\n<i>Koneksi ke local runtime aktif...</i>"
    if message_to_reply:
        status_msg = await message_to_reply.reply_text(initial_header, parse_mode=ParseMode.HTML, reply_markup=build_processing_keyboard())
    else:
        status_msg = await bot.send_message(chat_id=chat_id, text=initial_header, parse_mode=ParseMode.HTML, reply_markup=build_processing_keyboard())
    task = asyncio.create_task(stream_execution_worker(bot=bot, chat_id=chat_id, status_msg_id=status_msg.message_id, prompt=prompt, work_dir=work_dir, session_id=session_id, model=model, files=files))
    session_manager.active_tasks[chat_id] = task
    session_manager.task_start_times[chat_id] = time.monotonic()
    return True


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    try:
        from ....utils.path_resolver import extract_workdir_target, resolve_workdir_path
        target_candidate = extract_workdir_target(prompt)
        if target_candidate:
            current_wd = session_manager.get_chat_workdir(chat_id)
            resolved, dbg = resolve_workdir_path(target_candidate, current_workdir=current_wd)
            if resolved:
                session_manager.set_chat_workdir(chat_id, str(resolved))
                header = f"✅ <b>WORK_DIR diganti via chat natural language</b>\n<code>{html.escape(str(resolved))}</code>\n<i>Prompt:</i> <code>{html.escape(prompt[:100])}</code>"
                await msg.reply_text(header, parse_mode=ParseMode.HTML)
                from ....engine.file_explorer import file_explorer
                try:
                    tree_text, tree_kb = file_explorer.build_file_tree_ui(base_dir=str(resolved), current_subpath="", page=0)
                    await msg.reply_text(tree_text, parse_mode=ParseMode.HTML, reply_markup=tree_kb)
                except Exception:
                    pass
                log.info(f"Natural workdir switch chat={chat_id} -> {resolved} via '{prompt[:60]}'")
                return
            else:
                desktop_hint = Path.home() / "Desktop" / "RISET" / "Digitalisasi Karbon" / "HyperSpectral"
                hint_str = ""
                if desktop_hint.exists():
                    hint_str = f"\n\n💡 <b>Saran:</b> <code>/workdir {html.escape(str(desktop_hint))}</code>\natau <code>/workdir desktop/riset/digitalisasi karbon/hyperspectral</code>"
                await msg.reply_text(f"❌ <b>Gagal pindah direktori</b>\nTarget: <code>{html.escape(target_candidate)}</code>\n<i>{html.escape((dbg or '')[:400])}</i>{hint_str}\n\nCoba: <code>/workdir C:\\Path\\Lengkap</code> atau <code>/files</code> untuk jelajahi.", parse_mode=ParseMode.HTML)
                log.warning(f"Natural workdir miss chat={chat_id} target={target_candidate!r} dbg={dbg}")
                return
    except Exception as e:
        log.debug(f"workdir intercept error: {e}")
    await execute_prompt_task(bot=context.bot, chat_id=chat_id, prompt=prompt, message_to_reply=msg, files=None)
