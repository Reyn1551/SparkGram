"""
Unit Tests for Atomic File Operations and Session Manager.
"""
import os
import tempfile
import pytest
from pathlib import Path

from sparkgram.utils.atomic_file import atomic_write_text, atomic_write_json, safe_read_json
from sparkgram.utils.log_masker import mask_sensitive_text
from sparkgram.core.session_manager import SessionManager, fmt_time


def test_atomic_write_and_read():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test.json")
        data = {"key": "value", "count": 42}
        atomic_write_json(test_file, data)

        read_data = safe_read_json(test_file)
        assert read_data == data


def test_log_masker():
    raw_log = "Error in bot: bot8808398800:AAGG9aG3iupOpurz-lqJ7LghZC0-M2f9tsQ with key sk-1234567890abcdefghijklmn"
    masked = mask_sensitive_text(raw_log)
    assert "bot8808398800" not in masked
    assert "sk-1234567890" not in masked
    assert "[REDACTED_SECRET]" in masked


def test_session_manager_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / ".test_state.json"
        sm = SessionManager(state_file=state_file)
        
        # Set active session and workdir
        sm.set_active_session(chat_id=12345, session_id="ses_abc123")
        sm.set_chat_workdir(chat_id=12345, workdir=tmpdir)

        assert sm.get_active_session(12345) == "ses_abc123"
        assert sm.get_chat_workdir(12345) == str(Path(tmpdir).resolve())

        # Reload from disk
        sm_reloaded = SessionManager(state_file=state_file)
        assert sm_reloaded.get_active_session(12345) == "ses_abc123"
        assert sm_reloaded.get_chat_workdir(12345) == str(Path(tmpdir).resolve())
