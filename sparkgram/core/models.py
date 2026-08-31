"""
Core Data Models and Type Definitions for SparkGram.
"""
import html
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


class Priority(IntEnum):
    """Priority levels for the dispatcher queue."""
    P0_CANCEL = 0      # Cancellation, emergency abort signals
    P1_COMMAND = 1     # Interactive slash commands (/start, /model, buttons)
    P2_STREAM = 2      # Real-time streaming chunks and progress updates
    P3_BACKGROUND = 3  # Maintenance, cleanup, telemetry


@dataclass
class SessionInfo:
    """Represents an active or stored conversation session."""
    id: str
    title: str = "(tanpa judul)"
    work_dir: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    message_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Result of an executed subprocess or LLM call."""
    success: bool
    output: str
    error: Optional[str] = None
    return_code: int = 0
    duration_sec: float = 0.0
    tokens_used: int = 0


# Curated List of Preset Models
PRESET_MODELS: List[Dict[str, str]] = [
    {
        "id": "1",
        "alias": "spark",
        "name": "⚡ Muse Spark 1.2 (Default)",
        "model": "opencode/muse-spark-1.2-contributor-free",
        "desc": "Gratis & Cepat, SOTA reasoning (Default)",
    },
    {
        "id": "2",
        "alias": "groq",
        "name": "🦙 Groq Llama 3.3 70B",
        "model": "groq/llama-3.3-70b-versatile",
        "desc": "Ultra cepat (250+ t/s), gratis tier",
    },
    {
        "id": "3",
        "alias": "deepseek",
        "name": "🐳 DeepSeek V4 Flash",
        "model": "deepseek/deepseek-v4-flash",
        "desc": "Efisiensi tinggi, coding handal",
    },
    {
        "id": "4",
        "alias": "r1",
        "name": "🧠 DeepSeek R1",
        "model": "deepseek/deepseek-r1",
        "desc": "Complex reasoning & deep logic",
    },
    {
        "id": "5",
        "alias": "gpt4o-mini",
        "name": "🤖 OpenAI GPT-4o Mini",
        "model": "openai/gpt-4o-mini",
        "desc": "Hemat biaya, stabil & cerdas",
    },
    {
        "id": "6",
        "alias": "claude",
        "name": "💎 Claude 3.5 Sonnet",
        "model": "anthropic/claude-3-5-sonnet",
        "desc": "SOTA Coding & refactoring",
    },
    {
        "id": "7",
        "alias": "pickle",
        "name": "🥒 Big Pickle",
        "model": "opencode/big-pickle",
        "desc": "Alternatif model Opencode",
    },
]


def find_preset_model(query: str) -> Optional[Dict[str, str]]:
    """Finds a preset model by index, alias, or model string."""
    q = query.strip().lower()
    for item in PRESET_MODELS:
        if item["id"] == q:
            return item
        if item["alias"] == q:
            return item
        if item["model"].lower() == q or q in item["model"].lower():
            return item
        if q in item["name"].lower():
            return item
    return None


def build_models_html(active_model: str) -> str:
    """Builds HTML text listing available models with active indicator."""
    lines = [
        "🤖 <b>Pilih Model AI (1-Tap Switch)</b>\n",
        f"Model Aktif: <code>{html.escape(active_model)}</code> ✅\n",
        "<b>Daftar Model Tersedia:</b>"
    ]
    for m in PRESET_MODELS:
        is_active = (m["model"].lower() == active_model.lower())
        marker = " ✅ <b>[AKTIF]</b>" if is_active else ""
        lines.append(
            f"{m['id']}. <b>{m['name']}</b>{marker}\n"
            f"   <code>{html.escape(m['model'])}</code> • <i>{m['desc']}</i>"
        )
    lines.append("\n<i>Tap tombol di bawah atau ketik <code>/model 1</code> untuk ganti.</i>")
    return "\n".join(lines)


def build_models_keyboard(active_model: str) -> InlineKeyboardMarkup:
    """Builds interactive inline keyboard with 1-tap model switcher buttons."""
    buttons = []
    for m in PRESET_MODELS:
        is_active = (m["model"].lower() == active_model.lower())
        prefix = "✅ " if is_active else ""
        label = f"{prefix}{m['name']}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"mod:{m['id']}")])
    return InlineKeyboardMarkup(buttons)
