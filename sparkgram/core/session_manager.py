"""
Session Manager for SparkGram.
Handles session state persistence (.bridge_state.json), per-chat session and workdir mapping,
and opencode session interaction (list, rename, delete, fork, export).
"""
import os
import json
import html
import asyncio
import threading
import logging
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..config import settings
from ..utils.atomic_file import atomic_write_json, safe_read_json
from .models import SessionInfo

log = logging.getLogger(__name__)


def fmt_time(ms: int) -> str:
    """Format millisecond timestamp into readable date string."""
    try:
        dt = datetime.datetime.fromtimestamp(ms / 1000)
        return dt.strftime("%d/%m %H:%M")
    except Exception:
        return str(ms)


class SessionManager:
    """Manages active sessions, workdirs, and bridge state. Thread-safe via _lock."""

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or settings.state_file
        self._lock = threading.Lock()
        self.active_sessions: Dict[int, str] = {}
        self.chat_workdirs: Dict[int, str] = {}
        self.chat_workdir_history: Dict[int, List[str]] = {}
        self.last_msg_times: Dict[int, float] = {}
        self.active_tasks: Dict[int, asyncio.Task] = {}
        self.active_procs: Dict[int, Any] = {}
        self.task_start_times: Dict[int, float] = {}
        self.load_state()

    def load_state(self) -> None:
        """Loads active sessions and chat workdirs from state file. Thread-safe."""
        with self._lock:
            data = safe_read_json(str(self.state_file))
            raw_sessions = data.get("active_sessions", {})
            self.active_sessions = {int(k): str(v) for k, v in raw_sessions.items() if str(k).lstrip("-").isdigit()}
            raw_workdirs = data.get("chat_workdirs", {})
            self.chat_workdirs = {int(k): str(v) for k, v in raw_workdirs.items() if str(k).lstrip("-").isdigit()}
            raw_hist = data.get("chat_workdir_history", {})
            self.chat_workdir_history = {int(k): [str(x) for x in v if isinstance(x, str)] for k, v in raw_hist.items() if str(k).lstrip("-").isdigit() and isinstance(v, list)}
            if "runtime_model" in data:
                settings.runtime_model = data["runtime_model"]
            if "runtime_work_dir" in data:
                settings.runtime_work_dir = data["runtime_work_dir"]

    def save_state(self) -> None:
        """Atomically saves state to disk with Opt4 caps. Thread-safe."""
        with self._lock:
            cap = max(5, settings.max_sessions)
            if len(self.active_sessions) > cap:
                keys_to_keep = list(self.active_sessions.keys())[-cap:]
                self.active_sessions = {k: self.active_sessions[k] for k in keys_to_keep}
                log.info(f"Pruned active_sessions to {cap} (LRU)")
            if len(self.chat_workdirs) > cap * 2:
                keys_to_keep = list(self.chat_workdirs.keys())[-(cap * 2):]
                self.chat_workdirs = {k: self.chat_workdirs[k] for k in keys_to_keep}
            for cid in list(self.chat_workdir_history.keys()):
                if len(self.chat_workdir_history[cid]) > 20:
                    self.chat_workdir_history[cid] = self.chat_workdir_history[cid][-20:]
            data = {
                "active_sessions": {str(k): v for k, v in self.active_sessions.items()},
                "chat_workdirs": {str(k): v for k, v in self.chat_workdirs.items()},
                "chat_workdir_history": {str(k): v for k, v in self.chat_workdir_history.items()},
                "runtime_model": settings.runtime_model,
                "runtime_work_dir": settings.runtime_work_dir,
                "updated_at": datetime.datetime.now().isoformat(),
            }
            try:
                atomic_write_json(str(self.state_file), data)
            except Exception as e:
                log.error(f"Failed to save state: {e}")

    def cleanup_expired_state(self) -> None:
        """Opt4: remove stale workdir mappings whose dirs no longer exist or TTL exceeded."""
        try:
            if not self.state_file.exists():
                return
            mtime = self.state_file.stat().st_mtime
            age_days = (datetime.datetime.now().timestamp() - mtime) / 86400
            if age_days > settings.session_ttl_days:
                dead = [cid for cid, wd in self.chat_workdirs.items() if not Path(wd).exists()]
                if dead:
                    for cid in dead:
                        self.chat_workdirs.pop(cid, None)
                    log.info(f"Cleaned {len(dead)} dead workdirs (TTL {settings.session_ttl_days}d)")
                    self.save_state()
        except Exception as e:
            log.debug(f"cleanup_expired_state skip: {e}")

    def get_active_session(self, chat_id: int) -> Optional[str]:
        return self.active_sessions.get(chat_id)

    def set_active_session(self, chat_id: int, session_id: Optional[str]) -> None:
        if session_id:
            self.active_sessions[chat_id] = session_id
        else:
            self.active_sessions.pop(chat_id, None)
        self.save_state()

    def get_chat_workdir(self, chat_id: int) -> str:
        """Returns workdir for specific chat, falling back to global runtime_work_dir.
        Also attempts lazy reload from disk if chat_id missing in memory but present in file
        (fixes stale memory after another process wrote .bridge_state.json — e.g. duplicate poller race).
        """
        if chat_id not in self.chat_workdirs:
            try:
                data = safe_read_json(str(self.state_file))
                raw_wd = data.get("chat_workdirs", {})
                key = str(chat_id)
                if key in raw_wd and raw_wd[key]:
                    self.chat_workdirs[chat_id] = str(raw_wd[key])
                    # Sync runtime_work_dir if file has newer global
                    if data.get("runtime_work_dir"):
                        # Only sync if file's updated_at is recent (> memory); simplest: sync
                        settings.runtime_work_dir = data["runtime_work_dir"]
            except Exception:
                pass
        return self.chat_workdirs.get(chat_id, settings.runtime_work_dir)

    def set_chat_workdir(self, chat_id: int, workdir: str) -> None:
        resolved = str(Path(workdir).resolve())
        old = self.chat_workdirs.get(chat_id)
        if old and old != resolved:
            hist = self.chat_workdir_history.get(chat_id, [])
            hist.append(old)
            # cap 20
            if len(hist) > 20:
                hist = hist[-20:]
            self.chat_workdir_history[chat_id] = hist
        self.chat_workdirs[chat_id] = resolved
        # Update global fallback to last successful workdir (single-user convenience)
        # but keep per-chat isolation: global only affects chats without explicit mapping
        settings.runtime_work_dir = resolved
        self.save_state()
        log.info(f"WORK_DIR chat={chat_id} -> {resolved}")

    def pop_workdir_history(self, chat_id: int) -> Optional[str]:
        """Pops last workdir from history (cd -). Returns None if empty."""
        hist = self.chat_workdir_history.get(chat_id, [])
        if not hist:
            return None
        prev = hist.pop()
        self.chat_workdir_history[chat_id] = hist
        self.save_state()
        return prev

    def peek_workdir_history(self, chat_id: int) -> Optional[str]:
        hist = self.chat_workdir_history.get(chat_id, [])
        return hist[-1] if hist else None

    async def fetch_sessions(self, work_dir: Optional[str] = None, limit: int = 30, query: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches opencode sessions filtered by workdir and search query."""
        cmd = ["opencode", "session", "list", "--format", "json"]
        target_dir = work_dir or settings.runtime_work_dir
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            raw = stdout.decode("utf-8", errors="replace").strip()
            if not raw:
                return []
            data = json.loads(raw)
            norm_work = str(Path(target_dir).resolve()).lower() if target_dir else ""
            
            filtered = []
            for s in data:
                d = str(s.get("directory", "")).lower()
                if not norm_work or d == norm_work or norm_work in d or d in norm_work:
                    filtered.append(s)
            pool = filtered if filtered else data
            
            if query:
                q = query.lower().strip()
                pool = [s for s in pool if q in str(s.get("title", "")).lower() or q in str(s.get("id", "")).lower()]
                
            pool.sort(key=lambda x: x.get("updated", 0), reverse=True)
            return pool[:limit] if limit else pool
        except Exception as e:
            log.warning(f"fetch_sessions failed: {e}")
            return []

    async def rename_session(self, session_id: str, new_title: str) -> Tuple[bool, str]:
        """Renames a session in opencode."""
        cmd = ["opencode", "session", "rename", session_id, new_title]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            if proc.returncode == 0:
                return True, stdout.decode("utf-8", errors="replace").strip()
            return False, stderr.decode("utf-8", errors="replace").strip()
        except Exception as e:
            return False, str(e)

    async def delete_session(self, session_id: str) -> Tuple[bool, str]:
        """Deletes a session in opencode."""
        cmd = ["opencode", "session", "delete", session_id]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            if proc.returncode == 0:
                # Remove from active if present
                for cid, sid in list(self.active_sessions.items()):
                    if sid == session_id:
                        self.active_sessions.pop(cid, None)
                self.save_state()
                return True, stdout.decode("utf-8", errors="replace").strip()
            return False, stderr.decode("utf-8", errors="replace").strip()
        except Exception as e:
            return False, str(e)

    async def fork_session(self, session_id: str, message_id: Optional[str] = None) -> Tuple[bool, str]:
        """Forks a session in opencode."""
        cmd = ["opencode", "session", "fork", session_id]
        if message_id:
            cmd.append(message_id)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            out_str = stdout.decode("utf-8", errors="replace").strip()
            if proc.returncode == 0:
                return True, out_str
            return False, stderr.decode("utf-8", errors="replace").strip()
        except Exception as e:
            return False, str(e)

    async def export_session_to_markdown(self, session_id: str) -> Tuple[bool, str, str]:
        """Exports session messages to a clean markdown document. Returns (success, filepath, content)."""
        cmd = ["opencode", "export", session_id]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
            if proc.returncode != 0:
                return False, "", stderr.decode("utf-8", errors="replace").strip()
            
            raw = stdout.decode("utf-8", errors="replace").strip()
            export_dir = settings.log_dir / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)
            export_file = export_dir / f"session_{session_id}.md"
            
            with open(export_file, "w", encoding="utf-8") as f:
                f.write(raw)
            return True, str(export_file), raw
        except Exception as e:
            return False, "", str(e)


# Helper UI formatters for session listing
def build_sessions_html(sessions: List[Dict[str, Any]], active_id: Optional[str], page: int = 0, page_size: int = 10) -> str:
    if not sessions:
        return "<i>Belum ada session di direktori ini. Kirim pesan untuk buat baru.</i>"
    start = page * page_size
    slice_s = sessions[start:start + page_size]
    if not slice_s:
        return "<i>Tidak ada session di halaman ini.</i>"
    lines = []
    for idx, s in enumerate(slice_s, start + 1):
        sid = s.get("id", "")
        title = html.escape(s.get("title") or "(tanpa judul)")
        t = fmt_time(s.get("updated", 0) or s.get("created", 0))
        marker = " ✅ <b>AKTIF</b>" if sid == active_id else ""
        short = sid[-6:] if len(sid) > 6 else sid
        lines.append(f"{idx}. <b>{title}</b>{marker}\n   <code>{html.escape(sid)}</code> • <i>{t}</i> • <code>{short}</code>")
    total_pages = (len(sessions) + page_size - 1) // page_size
    footer = f"\n\n<i>Halaman {page + 1}/{max(1, total_pages)} • total {len(sessions)} session di WORK_DIR</i>" if total_pages > 1 else ""
    return "\n\n".join(lines) + footer


def build_sessions_keyboard(sessions: List[Dict[str, Any]], active_id: Optional[str], cols: int = 5, page: int = 0, page_size: int = 10) -> InlineKeyboardMarkup:
    """Builds inline paginated number grid keyboard."""
    kb = []
    start = page * page_size
    slice_s = sessions[start:start + page_size]
    row = []
    for idx, s in enumerate(slice_s, start + 1):
        sid = s.get("id", "")
        label = f"{'✅' if sid == active_id else ''}{idx}"
        row.append(InlineKeyboardButton(label.strip() or str(idx), callback_data=f"sw:{sid}"))
        if len(row) >= cols:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
        
    total_pages = (len(sessions) + page_size - 1) // page_size
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"sw:page:{page - 1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("Next ▶", callback_data=f"sw:page:{page + 1}"))
        if nav:
            kb.append(nav)
            
    kb.append([
        InlineKeyboardButton("🆕 New", callback_data="sw:new"),
        InlineKeyboardButton("🔄 Refresh", callback_data="sw:refresh"),
        InlineKeyboardButton("📁 Workdir", callback_data="sw:workdir"),
    ])
    return InlineKeyboardMarkup(kb)


# Global SessionManager singleton
session_manager = SessionManager()
