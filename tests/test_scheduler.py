"""
Unit and Integration Tests for SparkGram Self-Hosted Cron Scheduler.
"""
import os
import tempfile
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from sparkgram.scheduler.manager import (
    parse_cron_field,
    normalize_cron_expr,
    validate_cron,
    matches_now,
    CronScheduler,
)


def test_parse_cron_field_wildcard():
    res = parse_cron_field("*", 0, 59)
    assert len(res) == 60
    assert 0 in res and 59 in res


def test_parse_cron_field_single_and_list():
    res = parse_cron_field("5,10,15", 0, 59)
    assert res == {5, 10, 15}


def test_parse_cron_field_range():
    res = parse_cron_field("1-5", 0, 23)
    assert res == {1, 2, 3, 4, 5}


def test_parse_cron_field_step():
    res = parse_cron_field("*/15", 0, 59)
    assert res == {0, 15, 30, 45}


def test_parse_cron_field_range_step():
    res = parse_cron_field("10-30/10", 0, 59)
    assert res == {10, 20, 30}


def test_parse_cron_field_invalid():
    with pytest.raises(ValueError):
        parse_cron_field("60", 0, 59)
    with pytest.raises(ValueError):
        parse_cron_field("*/0", 0, 59)
    with pytest.raises(ValueError):
        parse_cron_field("5-2", 0, 23)


def test_normalize_shortcuts():
    assert normalize_cron_expr("@hourly") == "0 * * * *"
    assert normalize_cron_expr("@daily") == "0 0 * * *"
    assert normalize_cron_expr("@weekly") == "0 0 * * 0"
    assert normalize_cron_expr("@every 15m") == "*/15 * * * *"
    assert normalize_cron_expr("@every 2h") == "0 */2 * * *"


def test_validate_cron():
    ok, norm = validate_cron("*/5 * * * *")
    assert ok is True
    assert norm == "*/5 * * * *"

    ok, norm = validate_cron("@hourly")
    assert ok is True
    assert norm == "0 * * * *"

    ok, err = validate_cron("invalid cron")
    assert ok is False
    assert "Format cron harus 5 bagian" in err


def test_matches_now():
    # Freeze time: 2026-09-01 09:30:00 (Tuesday -> Python weekday=1 -> Cron dow=(1+1)%7=2)
    dt = datetime(2026, 9, 1, 9, 30, 0)

    # 1. Matches every minute
    assert matches_now("* * * * *", dt) is True

    # 2. Matches exact minute & hour
    assert matches_now("30 9 * * *", dt) is True
    assert matches_now("0 9 * * *", dt) is False

    # 3. Matches step minute
    assert matches_now("*/15 * * * *", dt) is True
    assert matches_now("*/20 * * * *", dt) is False

    # 4. Matches day of week (Tuesday = 2)
    assert matches_now("* * * * 2", dt) is True
    assert matches_now("* * * * 1", dt) is False


@pytest.mark.asyncio
async def test_cron_scheduler_crud():
    with tempfile.TemporaryDirectory() as tmpdir:
        sched = CronScheduler(base_dir=Path(tmpdir))

        # 1. Add job
        job = sched.add_job(
            chat_id=12345,
            cron_expr="0 9 * * *",
            prompt="Cek disk dan server health",
        )
        assert job["id"].startswith("job_")
        assert job["chat_id"] == 12345
        assert job["enabled"] is True

        # 2. List jobs
        jobs = sched.list_jobs(chat_id=12345)
        assert len(jobs) == 1
        assert jobs[0]["id"] == job["id"]

        # Other chat has 0 jobs
        assert len(sched.list_jobs(chat_id=99999)) == 0

        # 3. Toggle job
        new_state = sched.toggle_job(job["id"], chat_id=12345)
        assert new_state is False
        assert sched.get_job(job["id"])["enabled"] is False

        new_state = sched.toggle_job(job["id"], chat_id=12345)
        assert new_state is True

        # 4. Remove job
        removed = sched.remove_job(job["id"], chat_id=12345)
        assert removed is True
        assert len(sched.list_jobs(chat_id=12345)) == 0


@pytest.mark.asyncio
async def test_cron_scheduler_due_execution():
    with tempfile.TemporaryDirectory() as tmpdir:
        sched = CronScheduler(base_dir=Path(tmpdir))

        # Add job that matches every minute
        job = sched.add_job(
            chat_id=12345,
            cron_expr="* * * * *",
            prompt="Echo test",
        )

        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        # Mock execute_prompt_task
        from unittest.mock import patch
        with patch("sparkgram.bot.handlers.messages.execute_prompt_task", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = True

            due_count = await sched.check_and_run_due_jobs(mock_bot)
            assert due_count == 1

            # Second call in same minute should be skipped (deduplicated)
            due_count2 = await sched.check_and_run_due_jobs(mock_bot)
            assert due_count2 == 0


@pytest.mark.asyncio
async def test_schedule_and_jobs_commands():
    from telegram import User, Chat, Message, Update
    from sparkgram.config import settings
    from sparkgram.bot.handlers.commands import schedule_cmd, jobs_cmd, unschedule_cmd
    from sparkgram.scheduler.manager import cron_scheduler

    settings.allowed_user_ids = {100}
    user = User(id=100, first_name="Test", is_bot=False)
    chat = Chat(id=100, type="private")
    msg = MagicMock(spec=Message)
    msg.reply_text = AsyncMock()
    msg.text = "/schedule 0 9 * * * Cek git status"
    msg.from_user = user
    msg.chat = chat

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.effective_chat = chat
    update.effective_message = msg
    update.message = msg

    context = MagicMock()
    context.args = ["0", "9", "*", "*", "*", "Cek", "git", "status"]

    # 1. Test /schedule command
    await schedule_cmd(update, context)
    msg.reply_text.assert_called_once()
    reply_str = msg.reply_text.call_args[0][0]
    assert "Jadwal Tugas Berhasil Dibuat" in reply_str

    jobs = cron_scheduler.list_jobs(100)
    assert len(jobs) >= 1
    job_id = jobs[-1]["id"]

    # 2. Test /jobs command
    msg.reply_text.reset_mock()
    context.args = []
    await jobs_cmd(update, context)
    msg.reply_text.assert_called_once()
    reply_str = msg.reply_text.call_args[0][0]
    assert "Cron Task Scheduler" in reply_str
    assert job_id in reply_str

    # 3. Test /unschedule command
    msg.reply_text.reset_mock()
    context.args = [job_id]
    await unschedule_cmd(update, context)
    msg.reply_text.assert_called_once()
    reply_str = msg.reply_text.call_args[0][0]
    assert "berhasil dihapus" in reply_str

