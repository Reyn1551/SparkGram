"""
Persistent Memory Manager — Hermes parity for SparkGram.
Stores cross-session facts as inspectable markdown (memory/YYYY-MM-DD.md),
auto-summarized, searchable via substring, capped 50KB per file.
"""
import re
import html
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from ..config import settings

log = logging.getLogger(__name__)


class MemoryManager:
    """File-backed memory with markdown inspectability."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = (base_dir or settings.root_dir / "memory").resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _day_file(self, day: Optional[str] = None) -> Path:
        d = day or datetime.now().strftime("%Y-%m-%d")
        return self.base_dir / f"{d}.md"

    def add(self, text: str, chat_id: Optional[int] = None, tag: str = "fact") -> Path:
        """Appends one memory entry to today's file."""
        text = text.strip()
        if not text:
            raise ValueError("empty memory")
        if len(text) > 2000:
            text = text[:2000] + "…"
        ts = datetime.now().strftime("%H:%M:%S")
        chat_s = f" chat:{chat_id}" if chat_id else ""
        line = f"- [{ts}{chat_s}] **{tag}**: {text}\n"
        f = self._day_file()
        # Cap file at 50KB — rotate by truncating oldest 30%
        try:
            if f.exists() and f.stat().st_size > 50 * 1024:
                old = f.read_text(encoding="utf-8", errors="replace").splitlines()
                keep = old[int(len(old) * 0.3):]
                f.write_text("\n".join(keep) + "\n", encoding="utf-8")
        except Exception as e:
            log.debug(f"memory rotate skip: {e}")
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(line)
        return f

    def search(self, query: str, limit: int = 20) -> List[Dict[str, str]]:
        """Substring search across all memory files (case-insensitive)."""
        q = query.lower().strip()
        if not q:
            return []
        hits: List[Dict[str, str]] = []
        for f in sorted(self.base_dir.glob("*.md"), reverse=True):
            try:
                for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                    if q in line.lower():
                        hits.append({"day": f.stem, "line": line.strip()})
                        if len(hits) >= limit:
                            return hits
            except Exception as e:
                log.debug(f"memory search skip {f}: {e}")
        return hits

    def recent(self, days: int = 7, limit: int = 50) -> List[str]:
        """Returns recent memory lines (newest first)."""
        out: List[str] = []
        for f in sorted(self.base_dir.glob("*.md"), reverse=True)[:days]:
            try:
                for line in reversed(f.read_text(encoding="utf-8", errors="replace").splitlines()):
                    if line.strip().startswith("- ["):
                        out.append(f"{f.stem} {line.strip()}")
                        if len(out) >= limit:
                            return out
            except Exception:
                continue
        return out

    def stats(self) -> Dict[str, int]:
        files = list(self.base_dir.glob("*.md"))
        total_lines = 0
        total_bytes = 0
        for f in files:
            try:
                total_bytes += f.stat().st_size
                total_lines += len(f.read_text(encoding="utf-8", errors="replace").splitlines())
            except Exception:
                pass
        return {"files": len(files), "lines": total_lines, "bytes": total_bytes}

    def format_html(self, lines: List[str], header: str = "🧠 Memory") -> str:
        """Formats lines as Telegram HTML expandable blockquote."""
        if not lines:
            return f"<i>Belum ada memory.</i>"
        inner = html.escape("\n".join(lines[:30]), quote=False)
        return f"<blockquote expandable>\n<b>{html.escape(header)}</b>\n{inner}\n</blockquote>"

    def cleanup(self, keep_days: int = 30) -> int:
        """Deletes memory files older than keep_days. Returns deleted count."""
        cutoff = datetime.now() - timedelta(days=keep_days)
        deleted = 0
        for f in self.base_dir.glob("*.md"):
            try:
                dt = datetime.strptime(f.stem, "%Y-%m-%d")
                if dt < cutoff:
                    f.unlink()
                    deleted += 1
            except Exception:
                continue
        if deleted:
            log.info(f"Memory cleanup: {deleted} files >{keep_days}d removed")
        return deleted


memory_manager = MemoryManager()
