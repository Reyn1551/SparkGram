"""
Self-Hosted Cron Scheduler Engine for SparkGram.
Provides lightweight 5-field cron parsing (* * * * *), periodic task execution,
and atomic JSON persistence without heavy external dependencies.
"""
import os
import re
import html
import time
import uuid
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Set, Optional, Tuple, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from ..config import settings
from ..utils.atomic_file import safe_read_json, atomic_write_json

log = logging.getLogger(__name__)

# Standard cron shortcuts
CRON_SHORTCUTS = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}


def normalize_cron_expr(expr: str) -> str:
    """Normalizes cron shortcuts and spacing."""
    s = expr.strip()
    lower = s.lower()
    if lower in CRON_SHORTCUTS:
        return CRON_SHORTCUTS[lower]

    # Support @every Xm / @every Xh shortcut
    m_every_min = re.match(r"^@every\s+(\d+)\s*m(?:in|inute|inutes)?$", lower)
    if m_every_min:
        mins = int(m_every_min.group(1))
        if 1 <= mins <= 59:
            return f"*/{mins} * * * *"

    m_every_hr = re.match(r"^@every\s+(\d+)\s*h(?:r|our|ours)?$", lower)
    if m_every_hr:
        hrs = int(m_every_hr.group(1))
        if 1 <= hrs <= 23:
            return f"0 */{hrs} * * *"

    # Collapse multiple spaces into single space
    return re.sub(r"\s+", " ", s)


def parse_cron_field(field_str: str, min_val: int, max_val: int, is_dow: bool = False) -> Set[int]:
    """
    Parses a single cron field into a set of matching integer values.
    Supports *, numbers, comma-lists, ranges (X-Y), and steps (*/N, X-Y/N).
    """
    field_str = field_str.strip()
    if field_str == "*":
        return set(range(min_val, max_val + 1))

    matched: Set[int] = set()
    parts = field_str.split(",")

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if "/" in part:
            base, step_str = part.split("/", 1)
            if not step_str.isdigit():
                raise ValueError(f"Step tidak valid: {part}")
            step = int(step_str)
            if step <= 0:
                raise ValueError(f"Step harus lebih dari 0: {part}")

            if base == "*":
                rng_start, rng_end = min_val, max_val
            elif "-" in base:
                start_s, end_s = base.split("-", 1)
                rng_start, rng_end = int(start_s), int(end_s)
            else:
                rng_start = int(base)
                rng_end = max_val

            if not (min_val <= rng_start <= max_val and min_val <= rng_end <= max_val and rng_start <= rng_end):
                raise ValueError(f"Range di luar batas ({min_val}..{max_val}): {part}")

            for val in range(rng_start, rng_end + 1, step):
                if is_dow and val == 7:
                    val = 0
                matched.add(val)

        elif "-" in part:
            start_s, end_s = part.split("-", 1)
            if not (start_s.isdigit() and end_s.isdigit()):
                raise ValueError(f"Range tidak valid: {part}")
            start_val, end_val = int(start_s), int(end_s)
            if not (min_val <= start_val <= max_val and min_val <= end_val <= max_val and start_val <= end_val):
                raise ValueError(f"Range di luar batas ({min_val}..{max_val}): {part}")
            for val in range(start_val, end_val + 1):
                if is_dow and val == 7:
                    val = 0
                matched.add(val)

        else:
            if not part.isdigit():
                raise ValueError(f"Nilai tidak valid: {part}")
            val = int(part)
            if is_dow and val == 7:
                val = 0
            if not (min_val <= val <= max_val):
                raise ValueError(f"Nilai {val} di luar batas ({min_val}..{max_val})")
            matched.add(val)

    if not matched:
        raise ValueError(f"Field kosong atau tidak valid: {field_str}")

    return matched


def validate_cron(cron_expr: str) -> Tuple[bool, str]:
    """
    Validates 5-field cron expression.
    Returns (True, normalized_expr) or (False, error_message).
    """
    try:
        norm = normalize_cron_expr(cron_expr)
        fields = norm.split(" ")
        if len(fields) != 5:
            return False, f"Format cron harus 5 bagian (* * * * *), ditemukan {len(fields)} bagian."

        parse_cron_field(fields[0], 0, 59)              # Minute
        parse_cron_field(fields[1], 0, 23)              # Hour
        parse_cron_field(fields[2], 1, 31)              # Day of Month
        parse_cron_field(fields[3], 1, 12)              # Month
        parse_cron_field(fields[4], 0, 7, is_dow=True)  # Day of Week (0-7, 0 & 7 = Sun)

        return True, norm
    except Exception as e:
        return False, str(e)


def matches_now(cron_expr: str, dt: Optional[datetime] = None) -> bool:
    """Evaluates if the cron expression matches the given datetime (or now)."""
    try:
        norm = normalize_cron_expr(cron_expr)
        fields = norm.split(" ")
        if len(fields) != 5:
            return False

        cur = dt or datetime.now()

        # 1. Minute (0..59)
        if cur.minute not in parse_cron_field(fields[0], 0, 59):
            return False
        # 2. Hour (0..23)
        if cur.hour not in parse_cron_field(fields[1], 0, 23):
            return False
        # 3. Day of Month (1..31)
        if cur.day not in parse_cron_field(fields[2], 1, 31):
            return False
        # 4. Month (1..12)
        if cur.month not in parse_cron_field(fields[3], 1, 12):
            return False
        # 5. Day of Week: Python weekday (0=Mon..6=Sun) -> Cron dow (0=Sun, 1=Mon..6=Sat)
        cron_dow = (cur.weekday() + 1) % 7
        if cron_dow not in parse_cron_field(fields[4], 0, 7, is_dow=True):
            return False

        return True
    except Exception as e:
        log.debug(f"Cron match evaluation error ({cron_expr}): {e}")
        return False


class CronScheduler:
    """Lightweight self-hosted cron task manager with JSON persistence."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = (base_dir or settings.root_dir / "scheduler").resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_file = self.base_dir / "jobs.json"
        self._lock = asyncio.Lock()
        self._running_task: Optional[asyncio.Task] = None

    def _load_jobs(self) -> List[Dict[str, Any]]:
        """Reads jobs safely from JSON file."""
        data = safe_read_json(str(self.jobs_file), default=[])
        if isinstance(data, list):
            return data
        return []

    def _save_jobs(self, jobs: List[Dict[str, Any]]) -> None:
        """Persists jobs atomically to disk."""
        atomic_write_json(str(self.jobs_file), jobs)

    def list_jobs(self, chat_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Returns all jobs or filtered by chat_id."""
        jobs = self._load_jobs()
        if chat_id is not None:
            return [j for j in jobs if j.get("chat_id") == chat_id]
        return jobs

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Finds a job by its unique ID."""
        for j in self._load_jobs():
            if j.get("id") == job_id:
                return j
        return None

    def add_job(
        self,
        chat_id: int,
        cron_expr: str,
        prompt: str,
        work_dir: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validates and adds a new scheduled job.
        Raises ValueError if cron expression or prompt is invalid.
        """
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Prompt tugas tidak boleh kosong.")

        is_valid, norm_expr = validate_cron(cron_expr)
        if not is_valid:
            raise ValueError(f"Format cron tidak valid: {norm_expr}")

        job_id = f"job_{uuid.uuid4().hex[:6]}"
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        job: Dict[str, Any] = {
            "id": job_id,
            "chat_id": chat_id,
            "cron": norm_expr,
            "prompt": prompt,
            "work_dir": work_dir or str(settings.work_dir),
            "model": model or settings.runtime_model,
            "enabled": True,
            "created_at": now_iso,
            "last_run": None,
            "last_run_minute": None,
            "last_status": "pending",
        }

        jobs = self._load_jobs()
        jobs.append(job)
        self._save_jobs(jobs)
        log.info(f"Scheduled job added: {job_id} ({norm_expr}) for chat {chat_id}")
        return job

    def remove_job(self, job_id: str, chat_id: Optional[int] = None) -> bool:
        """Deletes a job by ID (and optional chat_id authorization)."""
        jobs = self._load_jobs()
        initial_len = len(jobs)
        new_jobs = [
            j for j in jobs
            if not (j.get("id") == job_id and (chat_id is None or j.get("chat_id") == chat_id))
        ]
        if len(new_jobs) < initial_len:
            self._save_jobs(new_jobs)
            log.info(f"Scheduled job removed: {job_id}")
            return True
        return False

    def toggle_job(self, job_id: str, chat_id: Optional[int] = None) -> Optional[bool]:
        """Toggles a job's enabled/paused state. Returns new state or None if not found."""
        jobs = self._load_jobs()
        for j in jobs:
            if j.get("id") == job_id and (chat_id is None or j.get("chat_id") == chat_id):
                j["enabled"] = not j.get("enabled", True)
                self._save_jobs(jobs)
                log.info(f"Scheduled job {job_id} toggled to enabled={j['enabled']}")
                return j["enabled"]
        return None

    def update_job_status(self, job_id: str, status: str, last_run: Optional[str] = None) -> None:
        """Updates last_run and last_status for a job."""
        jobs = self._load_jobs()
        for j in jobs:
            if j.get("id") == job_id:
                j["last_status"] = status
                if last_run:
                    j["last_run"] = last_run
                self._save_jobs(jobs)
                break

    async def execute_job(self, bot, job: Dict[str, Any]) -> None:
        """Executes a single scheduled job in the background and reports to Telegram."""
        from ..core.session_manager import session_manager
        from ..bot.handlers.messages import execute_prompt_task

        chat_id = job.get("chat_id")
        job_id = job.get("id")
        prompt = job.get("prompt", "")
        cron_expr = job.get("cron", "* * * * *")

        log.info(f"Triggering scheduled job {job_id} for chat {chat_id}: {prompt[:60]}")

        # Check if chat is currently busy
        if chat_id in session_manager.active_tasks and not session_manager.active_tasks[chat_id].done():
            log.warning(f"Job {job_id} skipped: Chat {chat_id} is busy with another active task.")
            self.update_job_status(job_id, status="skipped_busy")
            return

        # Announce job execution to Telegram
        header = (
            f"⏰ <b>[Cron Scheduler: <code>{job_id}</code>]</b>\n"
            f"Menjalankan tugas berkala (<code>{html.escape(cron_expr)}</code>):\n"
            f"<i>{html.escape(prompt)}</i>"
        )
        try:
            await bot.send_message(chat_id=chat_id, text=header, parse_mode=ParseMode.HTML)
        except Exception as e:
            log.warning(f"Failed to send scheduler notification to chat {chat_id}: {e}")

        # Execute prompt task
        try:
            ok = await execute_prompt_task(
                bot=bot,
                chat_id=chat_id,
                prompt=f"[SCHEDULED CRON JOB: {cron_expr}]\n{prompt}",
            )
            self.update_job_status(job_id, status="running" if ok else "failed_start")
        except Exception as e:
            log.error(f"Error executing scheduled job {job_id}: {e}", exc_info=e)
            self.update_job_status(job_id, status=f"error: {str(e)[:50]}")

    async def check_and_run_due_jobs(self, bot) -> int:
        """Checks all enabled jobs and dispatches those due in the current minute."""
        now = datetime.now()
        current_minute_key = now.strftime("%Y-%m-%d %H:%M")
        due_count = 0

        jobs = self._load_jobs()
        updated = False

        for job in jobs:
            if not job.get("enabled", True):
                continue

            cron_expr = job.get("cron", "")
            if not matches_now(cron_expr, now):
                continue

            # Prevent duplicate trigger within the same minute
            if job.get("last_run_minute") == current_minute_key:
                continue

            job["last_run_minute"] = current_minute_key
            job["last_run"] = now.strftime("%Y-%m-%d %H:%M:%S")
            job["last_status"] = "triggered"
            updated = True
            due_count += 1

            # Dispatch job execution asynchronously
            asyncio.create_task(self.execute_job(bot, job))

        if updated:
            self._save_jobs(jobs)

        return due_count

    async def start_scheduler_loop(self, bot_app_or_bot, interval_sec: int = 20) -> None:
        """Continuous background loop checking for due cron jobs."""
        log.info("Self-hosted Cron Scheduler loop started.")
        while True:
            try:
                bot = getattr(bot_app_or_bot, "bot", bot_app_or_bot)
                await self.check_and_run_due_jobs(bot)
            except asyncio.CancelledError:
                log.info("Cron Scheduler loop cancelled.")
                break
            except Exception as e:
                log.error(f"Error in Cron Scheduler loop: {e}", exc_info=e)
            await asyncio.sleep(interval_sec)

    # ---------------------------------------------------------
    # UI and Formatting Helpers
    # ---------------------------------------------------------
    def format_jobs_html(self, jobs: List[Dict[str, Any]], chat_id: Optional[int] = None) -> str:
        """Builds clean, structured HTML dashboard for scheduled jobs."""
        filtered = [j for j in jobs if chat_id is None or j.get("chat_id") == chat_id]
        total = len(filtered)
        active_count = sum(1 for j in filtered if j.get("enabled", True))

        if not filtered:
            return (
                "⏰ <b>Cron Task Scheduler</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "<i>Belum ada tugas terjadwal yang terdaftar.</i>\n\n"
                "<b>Cara Menambahkan Jadwal:</b>\n"
                "• <code>/schedule 0 9 * * * Cek git status dan test</code> (tiap jam 09:00)\n"
                "• <code>/schedule */30 * * * * Health check server</code> (tiap 30 menit)\n"
                "• <code>/schedule @daily Buat rekap commit harian</code>\n"
                "• <code>/schedule @hourly Cek port dan memory usage</code>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )

        text = (
            f"⏰ <b>Cron Task Scheduler</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>Total:</b> {total} jadwal (🟢 {active_count} aktif, ⏸️ {total - active_count} jeda)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )

        for j in filtered:
            j_id = j.get("id", "job")
            status_icon = "🟢" if j.get("enabled", True) else "⏸️"
            status_lbl = "Aktif" if j.get("enabled", True) else "Dijeda"
            cron = j.get("cron", "* * * * *")
            prompt = j.get("prompt", "")
            prompt_short = prompt[:75] + ("..." if len(prompt) > 75 else "")
            last_run = j.get("last_run") or "<i>(belum pernah jalan)</i>"
            last_stat = j.get("last_status", "pending")

            text += (
                f"{status_icon} <b><code>{j_id}</code></b> • <code>{html.escape(cron)}</code> ({status_lbl})\n"
                f"📝 <i>{html.escape(prompt_short)}</i>\n"
                f"🕒 Terakhir: {last_run} • Status: <code>{html.escape(str(last_stat))}</code>\n\n"
            )

        text += "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        text += "💡 <i>Ketik <code>/unschedule [id]</code> untuk menghapus, atau gunakan tombol di bawah:</i>"
        return text

    def build_jobs_keyboard(self, jobs: List[Dict[str, Any]], chat_id: Optional[int] = None) -> InlineKeyboardMarkup:
        """Constructs interactive inline keyboard for managing scheduled jobs."""
        filtered = [j for j in jobs if chat_id is None or j.get("chat_id") == chat_id]
        buttons: List[List[InlineKeyboardButton]] = []

        for j in filtered[:8]:
            j_id = j.get("id", "job")
            is_enabled = j.get("enabled", True)
            toggle_label = "⏸️ Jeda" if is_enabled else "▶️ Aktifkan"

            buttons.append([
                InlineKeyboardButton(f"{toggle_label} {j_id}", callback_data=f"job:tog:{j_id}"),
                InlineKeyboardButton(f"🚀 Run", callback_data=f"job:run:{j_id}"),
                InlineKeyboardButton(f"🗑️ Hapus", callback_data=f"job:del:{j_id}"),
            ])

        buttons.append([
            InlineKeyboardButton("🔄 Refresh", callback_data="job:list"),
            InlineKeyboardButton("📖 Panduan Format", callback_data="job:help"),
        ])

        return InlineKeyboardMarkup(buttons)


# Global singleton instance
cron_scheduler = CronScheduler()
