"""Message utils — extracted from messages.py for 10/10 modularity."""
import html
import datetime
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_short_model_name(model_str: str) -> str:
    if not model_str:
        return "AI"
    if "/" in model_str:
        return model_str.split("/")[-1]
    return model_str


def get_short_dir(path_str: str) -> str:
    try:
        p = Path(path_str).resolve()
        parts = p.parts
        if len(parts) > 2:
            return f".../{parts[-2]}/{parts[-1]}"
        return str(p)
    except Exception:
        return str(path_str)[:80]


def get_current_time_str() -> str:
    try:
        return datetime.datetime.now().strftime("%H:%M:%S")
    except Exception:
        return ""


def build_response_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🆕 Sesi Baru", callback_data="sw:new"), InlineKeyboardButton("📁 Switch Sesi", callback_data="sw:refresh")],
        [InlineKeyboardButton("🤖 Ganti Model", callback_data="hlth:model"), InlineKeyboardButton("🏥 Health Telemetri", callback_data="hlth:refresh")],
    ])


def build_processing_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛑 Batalkan Job", callback_data="act:cancel"), InlineKeyboardButton("📜 Cek Log", callback_data="hlth:logs")],
    ])
