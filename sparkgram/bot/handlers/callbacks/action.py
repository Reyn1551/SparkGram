"""Action callbacks (act:) — extracted from callbacks.py"""
from telegram.constants import ParseMode

from ....core.session_manager import session_manager


async def handle(query, context, chat_id: int, work_dir: str, payload: str) -> bool:
    payload = payload.strip()

    if payload == "cancel":
        from ....engine.process_tree import process_supervisor
        cancelled_any = False
        proc = session_manager.active_procs.pop(chat_id, None)
        if proc:
            await process_supervisor.kill_process_tree(proc)
            cancelled_any = True
        task = session_manager.active_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()
            cancelled_any = True
        if cancelled_any:
            await query.answer("🛑 Job dibatalkan.", show_alert=False)
            try:
                await query.edit_message_text("🛑 <b>Job berhasil dibatalkan oleh pengguna via tombol.</b>\n<i>Subproses telah dimatikan secara bersih.</i>", parse_mode=ParseMode.HTML)
            except Exception:
                pass
        else:
            await query.answer("Tidak ada job aktif yang sedang berjalan.", show_alert=True)
        return True

    if payload == "close":
        await query.answer("🗑️ Pesan ditutup.")
        try:
            await query.message.delete()
        except Exception:
            try:
                await query.edit_message_text("<i>(Pesan ditutup)</i>", parse_mode=ParseMode.HTML)
            except Exception:
                pass
        return True

    return False
