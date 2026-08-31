"""
End-to-End Smoke and Integration Tests for SparkGram v1.0.
"""
import os
import json
import pytest
from unittest.mock import patch, MagicMock

from sparkgram.config import settings
from sparkgram.adapters.opencode_adapter import OpenCodeAdapter, clean_ansi
from sparkgram.adapters.voice_adapter import VoiceAdapter
from sparkgram.core.session_manager import session_manager
from sparkgram.cli.wizard import validate_telegram_token


def test_opencode_adapter_command_builder():
    cmd = OpenCodeAdapter.build_run_command(
        prompt="buat file hello.py",
        work_dir="C:/TestProject",
        model="groq/llama-3.3-70b-versatile",
        session_id="ses_12345",
        auto_approve=True,
    )
    assert "opencode" == cmd[0]
    assert "run" == cmd[1]
    assert "buat file hello.py" in cmd
    assert "--dir" in cmd
    assert "C:/TestProject" in cmd
    assert "--model" in cmd
    assert "groq/llama-3.3-70b-versatile" in cmd
    assert "--session" in cmd
    assert "ses_12345" in cmd
    assert "--auto" in cmd


def test_clean_ansi_codes():
    colored_text = "\x1b[32m[SUCCESS]\x1b[0m File created: \x1b[1;34msrc/main.py\x1b[0m"
    cleaned = clean_ansi(colored_text)
    assert cleaned == "[SUCCESS] File created: src/main.py"
    assert "\x1b" not in cleaned


@pytest.mark.asyncio
async def test_voice_adapter_missing_key():
    # When no key is provided and none in env
    with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
        ok, msg = await VoiceAdapter.transcribe_audio_bytes(b"dummy_bytes", groq_api_key="")
        assert ok is False
        assert "GROQ_API_KEY" in msg


def test_validate_telegram_token_mock():
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "ok": True,
        "result": {"id": 123456789, "is_bot": True, "username": "MySparkGramBot"}
    }).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        ok, username, info = validate_telegram_token("123456789:ABCdefGHIjklMNO")
        assert ok is True
        assert username == "MySparkGramBot"
        assert info["id"] == 123456789
