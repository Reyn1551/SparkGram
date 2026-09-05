"""Scheduler callbacks (job:) — extracted from callbacks.py"""
import asyncio
from telegram.constants import ParseMode


async def handle(query, context, chat_id: int, work_dir: str, payload: str) -> bool:
    from ....scheduler.manager import cron_scheduler
    payload = payload.strip()

    if payload == "list":
        await query.answer("🔄 Memperbarui daftar tugas...")
        jobs = cron_scheduler.list_jobs(chat_id)
        text = cron_scheduler.format_jobs_html(jobs, chat_id=chat_id)
        kb = cron_scheduler.build_jobs_keyboard(jobs, chat_id=chat_id)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if payload.startswith("tog:"):
        job_id = payload[4:]
        new_state = cron_scheduler.toggle_job(job_id, chat_id=chat_id)
        if new_state is not None:
            lbl = "🟢 Jadwal diaktifkan!" if new_state else "⏸️ Jadwal dijeda!"
            await query.answer(lbl)
            jobs = cron_scheduler.list_jobs(chat_id)
            text = cron_scheduler.format_jobs_html(jobs, chat_id=chat_id)
            kb = cron_scheduler.build_jobs_keyboard(jobs, chat_id=chat_id)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
        else:
            await query.answer("❌ Jadwal tidak ditemukan", show_alert=True)
        return True

    if payload.startswith("del:"):
        job_id = payload[4:]
        ok = cron_scheduler.remove_job(job_id, chat_id=chat_id)
        await query.answer("🗑️ Jadwal berhasil dihapus!" if ok else "❌ Gagal menghapus jadwal", show_alert=True)
        jobs = cron_scheduler.list_jobs(chat_id)
        text = cron_scheduler.format_jobs_html(jobs, chat_id=chat_id)
        kb = cron_scheduler.build_jobs_keyboard(jobs, chat_id=chat_id)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if payload.startswith("run:"):
        job_id = payload[4:]
        job = cron_scheduler.get_job(job_id)
        if job:
            await query.answer(f"🚀 Menjalankan {job_id} sekarang...")
            asyncio.create_task(cron_scheduler.execute_job(context.bot, job))
        else:
            await query.answer("❌ Jadwal tidak ditemukan", show_alert=True)
        return True

    if payload == "help":
        await query.answer("Format Cron 5-Bagian")
        help_text = (
            "📖 <b>Panduan Format Cron 5-Bagian</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<code>* * * * *</code>\n"
            "┬ ┬ ┬ ┬ ┬\n"
            "│ │ │ │ └─ Hari dalam Minggu (0-7, 0 & 7 = Minggu)\n"
            "│ │ │ └─── Bulan (1-12)\n"
            "│ │ └───── Tanggal dalam Bulan (1-31)\n"
            "│ └─────── Jam (0-23)\n"
            "└───────── Menit (0-59)\n\n"
            "<b>Contoh Praktis:</b>\n"
            "• <code>0 9 * * 1-5</code> — Setiap hari kerja jam 09:00 WIB\n"
            "• <code>*/15 * * * *</code> — Setiap 15 menit\n"
            "• <code>0 */2 * * *</code> — Setiap 2 jam sekali\n"
            "• <code>@daily</code> — Setiap hari jam 00:00\n"
            "• <code>@hourly</code> — Setiap awal jam\n"
            "• <code>@every 10m</code> — Setiap interval 10 menit\n\n"
            "<b>Gunakan:</b> <code>/schedule [cron] [prompt]</code>"
        )
        await context.bot.send_message(chat_id=chat_id, text=help_text, parse_mode=ParseMode.HTML)
        return True

    return False
