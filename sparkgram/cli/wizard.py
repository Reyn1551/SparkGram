"""
Interactive 60-Second Setup Wizard for SparkGram.
Validates BotFather token via Telegram getMe API and establishes instant pairing.
"""
import os
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

from ..config import settings, ROOT_DIR, ENV_FILE
from ..utils.atomic_file import atomic_write_text


def validate_telegram_token(token: str) -> tuple[bool, str, dict]:
    """Validates Telegram bot token by querying getMe endpoint."""
    url = f"https://api.telegram.org/bot{token}/getMe"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                result = data.get("result", {})
                username = result.get("username", "UnknownBot")
                return True, username, result
            return False, "Token ditolak oleh Telegram API.", {}
    except urllib.error.HTTPError as e:
        return False, f"HTTP Error {e.code}: Token tidak valid.", {}
    except Exception as e:
        return False, f"Koneksi gagal: {e}", {}


def run_setup_wizard():
    """Interactive CLI wizard for new users."""
    print("=" * 60)
    print("✨ Selamat Datang di SparkGram — 60-Second Setup Wizard ✨")
    print("=" * 60)
    print("1. Buka Telegram dan cari @BotFather")
    print("2. Kirim perintah /newbot dan salin HTTP API Token yang diberikan\n")

    current_token = settings.telegram_bot_token
    token = input(f"Masukkan Telegram Bot Token [{current_token[:8]}...]: ").strip() or current_token

    if not token:
        print("❌ Error: Token tidak boleh kosong.")
        sys.exit(1)

    print("\n⏳ Memvalidasi token ke Telegram API...")
    ok, username, info = validate_telegram_token(token)
    if not ok:
        print(f"❌ {username}")
        sys.exit(1)

    print(f"✅ Token Terverifikasi! Terhubung ke: @{username} (ID: {info.get('id')})\n")

    # Detect active directory
    default_dir = str(Path.cwd().resolve())
    work_dir = input(f"WORK_DIR default [{default_dir}]: ").strip() or default_dir

    env_content = f"""TELEGRAM_BOT_TOKEN={token}
MODEL=opencode/muse-spark-1.2-contributor-free
WORK_DIR={work_dir}
ALLOWED_USER_IDS=
WEBHOOK_URL=
ENABLE_AUTO_RESTART=1
FEATURE_WORKDIR=1
FEATURE_SESSIONS=1
FEATURE_CLEANUP=1
FEATURE_VOICE=1
FEATURE_DOC=1
FEATURE_QUEUE=1
FALLBACK_MODEL=groq/llama-3.3-70b-versatile
MAX_BACKOFF=5
RATE_LIMIT_SEC=1.2
"""
    atomic_write_text(str(ENV_FILE), env_content)
    print(f"✅ Konfigurasi disimpan ke {ENV_FILE}")
    print("\n🎉 Setup Selesai! Jalankan SparkGram sekarang:")
    print("   python -m sparkgram")
    print(f"\nBuka bot kamu di Telegram: https://t.me/{username}\n")


if __name__ == "__main__":
    run_setup_wizard()
