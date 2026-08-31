"""
Configuration and Environment Settings for SparkGram.
"""
import os
import sys
from pathlib import Path
from typing import Set, List, Optional
from dotenv import load_dotenv

# Base paths
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"
STATE_FILE = ROOT_DIR / ".bridge_state.json"

# Load environment variables
if ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=True)
else:
    load_dotenv(override=True)


class Settings:
    """Centralized Settings class with live reload and validation."""
    
    def __init__(self):
        self.reload()

    def reload(self):
        # Telegram Bot Token
        self.telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        
        # Allowed Users
        allowed_raw = os.getenv("ALLOWED_USER_IDS", "")
        self.allowed_user_ids: Set[int] = set()
        for part in allowed_raw.replace(";", ",").split(","):
            part = part.strip()
            if part.isdigit():
                self.allowed_user_ids.add(int(part))
                
        # Base Work Directory
        raw_work_dir = os.getenv("WORK_DIR", "").strip()
        if not raw_work_dir:
            raw_work_dir = str(ROOT_DIR)
        self.work_dir: str = str(Path(raw_work_dir).resolve())
        self.runtime_work_dir: str = self.work_dir
        
        # Models
        self.model: str = os.getenv("MODEL", "opencode/muse-spark-1.2-contributor-free").strip()
        self.runtime_model: str = self.model
        self.fallback_model: str = os.getenv("FALLBACK_MODEL", "groq/llama-3.3-70b-versatile").strip()
        
        # Webhook / Polling
        self.webhook_url: Optional[str] = os.getenv("WEBHOOK_URL", "").strip() or None
        self.webhook_secret: str = os.getenv("WEBHOOK_SECRET", "sparkgram-secret-key").strip()
        self.port: int = int(os.getenv("PORT", "8000"))
        
        # Feature Flags
        self.enable_auto_restart: bool = os.getenv("ENABLE_AUTO_RESTART", "1").strip().lower() in ("1", "true", "yes")
        self.feature_workdir: bool = os.getenv("FEATURE_WORKDIR", "1").strip().lower() in ("1", "true", "yes")
        self.feature_sessions: bool = os.getenv("FEATURE_SESSIONS", "1").strip().lower() in ("1", "true", "yes")
        self.feature_cleanup: bool = os.getenv("FEATURE_CLEANUP", "1").strip().lower() in ("1", "true", "yes")
        self.feature_voice: bool = os.getenv("FEATURE_VOICE", "1").strip().lower() in ("1", "true", "yes")
        self.feature_doc: bool = os.getenv("FEATURE_DOC", "1").strip().lower() in ("1", "true", "yes")
        self.feature_queue: bool = os.getenv("FEATURE_QUEUE", "1").strip().lower() in ("1", "true", "yes")
        
        # Rate Limits & Buffering (Opt3: 1.5s throttle to avoid 429)
        self.max_backoff: float = float(os.getenv("MAX_BACKOFF", "5.0"))
        self.rate_limit_sec: float = float(os.getenv("RATE_LIMIT_SEC", "1.5"))
        self.global_rate_limit: float = float(os.getenv("GLOBAL_RATE_LIMIT", "28.0"))
        self.max_sessions: int = int(os.getenv("MAX_SESSIONS", "20"))
        self.session_ttl_days: int = int(os.getenv("SESSION_TTL_DAYS", "7"))
        
        # Logging & Temp directory
        temp_base = os.getenv("TEMP") or os.getenv("TMP") or "/tmp"
        self.log_dir: Path = Path(temp_base) / "telegram-bridge"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file: Path = self.log_dir / "bridge.log"
        self.state_file: Path = STATE_FILE
        self.root_dir: Path = ROOT_DIR


# Singleton instance
settings = Settings()
