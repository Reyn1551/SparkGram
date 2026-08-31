"""
Log and Text Masker for SparkGram.
Strips and redacts sensitive credentials from log streams and error tracebacks.
"""
import re
from typing import List, Pattern

# Regular expressions matching credentials and tokens
TOKEN_PATTERNS: List[Pattern] = [
    re.compile(r"bot\d{6,12}:[A-Za-z0-9_-]{35,}", re.IGNORECASE),
    re.compile(r"\d{6,12}:[A-Za-z0-9_-]{35,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"gsk_[A-Za-z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"ghp_[A-Za-z0-9_-]{36,}", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}", re.IGNORECASE),
]


def mask_sensitive_text(text: str) -> str:
    """Masks secrets and tokens from text before logging or outputting."""
    if not text:
        return ""
    masked = str(text)
    for pat in TOKEN_PATTERNS:
        masked = pat.sub("[REDACTED_SECRET]", masked)
    return masked
