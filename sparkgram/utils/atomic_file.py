"""
Atomic File Utilities for SparkGram.
Ensures zero partial writes and corruption-proof state persistence.
"""
import os
import json
import logging
import tempfile
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


def atomic_write_text(filepath: str, content: str, encoding: str = "utf-8") -> None:
    """Writes content to a temporary file first, then atomically replaces target file."""
    dir_name = os.path.dirname(filepath) or "."
    os.makedirs(dir_name, exist_ok=True)
    
    # Create temp file in the same directory to guarantee atomic replace across filesystems
    fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_atomic_", text=True)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, filepath)
    except Exception:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError as e:
                log.debug(f"Temp cleanup skip {temp_path}: {e}")
        raise


def atomic_write_json(filepath: str, data: Any, indent: int = 2) -> None:
    """Serializes data to JSON and atomically writes to file."""
    serialized = json.dumps(data, indent=indent, ensure_ascii=False)
    atomic_write_text(filepath, serialized)


def safe_read_json(filepath: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Reads JSON from file safely; returns default on file missing or corrupt."""
    if default is None:
        default = {}
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default
