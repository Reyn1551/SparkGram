"""
Interactive File Explorer & Artifact Delivery Service for SparkGram.
Provides chroot-jailed file browsing, 64-byte safe LRU callback state mapping, zip generation, and safe file uploads.
"""
import os
import io
import time
import html
import shutil
import zipfile
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

log = logging.getLogger(__name__)

# Exclude list for safe zip archiving and tree inspection
DEFAULT_EXCLUDES = {
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "env",
    ".cache",
    ".env",
    ".idea",
    ".vscode",
}


class ExplorerStateCache:
    """In-memory bidirectional LRU cache to keep Telegram callback_data strictly < 64 bytes."""

    def __init__(self, max_items: int = 500):
        self._cache: Dict[str, str] = {}
        self._reverse_cache: Dict[str, str] = {}
        self._counter: int = 0
        self._max_items: int = max_items

    def register_path(self, path_str: str) -> str:
        """Returns short hexadecimal token for given path."""
        norm_path = path_str.replace("\\", "/").strip("/")
        if not norm_path:
            norm_path = "."

        if norm_path in self._reverse_cache:
            return self._reverse_cache[norm_path]

        token = f"{self._counter:x}"
        self._counter += 1

        if len(self._cache) >= self._max_items:
            oldest_token = next(iter(self._cache))
            old_path = self._cache.pop(oldest_token)
            self._reverse_cache.pop(old_path, None)

        self._cache[token] = norm_path
        self._reverse_cache[norm_path] = token
        return token

    def get_path(self, token: str) -> Optional[str]:
        """Retrieves normalized path from token."""
        return self._cache.get(token)


state_cache = ExplorerStateCache()


class FileExplorerService:
    """Safe Chroot-Jailed File Explorer & Artifact Service."""

    @staticmethod
    def safe_resolve(base_dir: str, rel_path: str = "") -> Path:
        """Strictly resolves target path inside base_dir sandbox (prevents Path Traversal)."""
        base = Path(base_dir).resolve()
        clean_rel = rel_path.replace("\\", "/").strip("/")
        target = (base / clean_rel).resolve()

        if not target.is_relative_to(base):
            raise PermissionError(f"Akses ditolak: Path di luar sandbox workspace ({rel_path}).")

        if target.is_symlink():
            resolved_sym = target.resolve()
            if not resolved_sym.is_relative_to(base):
                raise PermissionError("Akses ditolak: Symlink mengarah ke luar workspace.")

        return target

    @classmethod
    def build_file_tree_ui(
        cls,
        base_dir: str,
        current_subpath: str = "",
        page: int = 0,
        page_size: int = 6,
    ) -> Tuple[str, InlineKeyboardMarkup]:
        """Builds Telegram HTML text and inline keyboard for browsing directory."""
        try:
            target = cls.safe_resolve(base_dir, current_subpath)
        except Exception as e:
            return f"❌ <b>Error:</b> {html.escape(str(e))}", InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Root", callback_data="fe:cd:root")]
            ])

        if not target.exists() or not target.is_dir():
            return "❌ <b>Folder tidak ditemukan.</b>", InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Root", callback_data="fe:cd:root")]
            ])

        # Read directory entries
        try:
            raw_entries = [e for e in target.iterdir() if e.name not in DEFAULT_EXCLUDES]
        except PermissionError:
            return "❌ <b>Izin akses folder ditolak oleh OS.</b>", InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Root", callback_data="fe:cd:root")]
            ])

        # Sort: directories first, then files
        raw_entries.sort(key=lambda x: (not x.is_dir(), x.name.lower()))

        total_items = len(raw_entries)
        total_pages = max(1, (total_items + page_size - 1) // page_size)
        page = max(0, min(page, total_pages - 1))

        start_idx = page * page_size
        page_entries = raw_entries[start_idx : start_idx + page_size]

        rel_display = "/" + str(target.relative_to(Path(base_dir).resolve())).replace("\\", "/")
        if rel_display in ("/", "/."):
            rel_display = "/"

        text = (
            f"📁 <b>File Explorer:</b> <code>{html.escape(rel_display)}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        buttons: List[List[InlineKeyboardButton]] = []
        base_resolved = Path(base_dir).resolve()

        if not page_entries:
            text += "<i>(Folder kosong)</i>\n"

        for entry in page_entries:
            sub = str(entry.relative_to(base_resolved)).replace("\\", "/")
            token = state_cache.register_path(sub)

            if entry.is_dir():
                text += f"📁 <b>{html.escape(entry.name)}/</b>\n"
                buttons.append([
                    InlineKeyboardButton(f"📁 {entry.name}/", callback_data=f"fe:cd:{token}"),
                    InlineKeyboardButton("📦 Zip", callback_data=f"fe:zip:{token}"),
                ])
            else:
                try:
                    size_kb = entry.stat().st_size / 1024
                    size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
                except Exception:
                    size_str = "N/A"
                text += f"📄 {html.escape(entry.name)} <i>({size_str})</i>\n"
                buttons.append([
                    InlineKeyboardButton(f"📄 {entry.name}", callback_data=f"fe:vw:{token}"),
                    InlineKeyboardButton("📥 Unduh", callback_data=f"fe:dl:{token}"),
                ])

        text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n<i>Total: {total_items} item • Hal {page+1}/{total_pages}</i>"

        # Action row
        current_token = state_cache.register_path(current_subpath)
        nav_row: List[InlineKeyboardButton] = []

        if current_subpath and current_subpath not in (".", ""):
            # Parent path
            parent_rel = str(target.parent.relative_to(base_resolved)).replace("\\", "/") if target != base_resolved else "."
            parent_token = state_cache.register_path(parent_rel)
            nav_row.append(InlineKeyboardButton("⬆️ Up", callback_data=f"fe:cd:{parent_token}"))

        nav_row.append(InlineKeyboardButton("🔄 Refresh", callback_data=f"fe:rf:{current_token}"))
        nav_row.append(InlineKeyboardButton("📦 Zip Folder", callback_data=f"fe:zip:{current_token}"))
        buttons.append(nav_row)

        # Pagination row
        if total_pages > 1:
            p_row: List[InlineKeyboardButton] = []
            if page > 0:
                p_row.append(InlineKeyboardButton("◀ Prev", callback_data=f"fe:p:{current_token}:{page-1}"))
            p_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="fe:noop"))
            if page < total_pages - 1:
                p_row.append(InlineKeyboardButton("Next ▶", callback_data=f"fe:p:{current_token}:{page+1}"))
            buttons.append(p_row)

        return text, InlineKeyboardMarkup(buttons)

    @classmethod
    def read_file_preview(cls, base_dir: str, rel_path: str, max_lines: int = 50) -> Tuple[bool, str]:
        """Reads snippet of a text file with line numbers and safe HTML formatting."""
        try:
            target = cls.safe_resolve(base_dir, rel_path)
        except Exception as e:
            return False, f"Akses ditolak: {e}"

        if not target.exists() or not target.is_file():
            return False, "File tidak ditemukan."

        size_kb = target.stat().st_size / 1024
        if size_kb > 2048:
            return False, f"File terlalu besar untuk preview ({size_kb:.1f} KB). Gunakan tombol Unduh."

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return False, f"Gagal membaca file: {e}"

        lines = content.splitlines()
        truncated = len(lines) > max_lines
        preview_lines = lines[:max_lines]

        formatted_lines = []
        for i, line in enumerate(preview_lines, start=1):
            formatted_lines.append(f"{i:3d} | {line}")

        body = "\n".join(formatted_lines)
        if truncated:
            body += f"\n... (menampilkan {max_lines} dari {len(lines)} baris — gunakan Unduh untuk file lengkap)"

        ext = target.suffix.lstrip(".") or "txt"
        header = (
            f"📄 <b>{html.escape(target.name)}</b> <i>({size_kb:.1f} KB)</i>\n"
            f"📁 <code>{html.escape(rel_path)}</code>\n\n"
        )
        return True, header + f"<blockquote expandable><pre><code class=\"language-{html.escape(ext)}\">{html.escape(body)}</code></pre></blockquote>"

    @classmethod
    def create_safe_zip(
        cls,
        base_dir: str,
        rel_path: str = "",
        max_size_bytes: int = 50 * 1024 * 1024,
    ) -> Tuple[bool, Optional[bytes], str]:
        """
        Creates clean in-memory zip archive of folder or file, excluding heavy/sensitive caches.
        Returns (success, zip_bytes, filename_or_error).
        """
        try:
            target = cls.safe_resolve(base_dir, rel_path)
        except Exception as e:
            return False, None, f"Akses ditolak: {e}"

        if not target.exists():
            return False, None, "Target tidak ditemukan."

        zip_buffer = io.BytesIO()
        total_uncompressed = 0
        file_count = 0
        max_files = 1000

        try:
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                if target.is_file():
                    zf.write(target, arcname=target.name)
                    zip_name = f"{target.stem}.zip"
                else:
                    for root, dirs, files in os.walk(target):
                        # Filter out excluded directory names in-place
                        dirs[:] = [d for d in dirs if d not in DEFAULT_EXCLUDES]

                        for file in files:
                            if file in DEFAULT_EXCLUDES or file.endswith((".pyc", ".tmp")):
                                continue

                            file_path = Path(root) / file
                            try:
                                sz = file_path.stat().st_size
                                total_uncompressed += sz
                                file_count += 1
                            except Exception:
                                continue

                            if total_uncompressed > max_size_bytes or file_count > max_files:
                                return False, None, f"Ukuran file melebihi batas aman ({max_size_bytes // 1024 // 1024} MB)."

                            rel_arc = file_path.relative_to(target)
                            zf.write(file_path, arcname=str(rel_arc))

                    zip_name = f"{target.name if target.name else 'workspace'}.zip"

            zip_buffer.seek(0)
            return True, zip_buffer.getvalue(), zip_name
        except Exception as e:
            return False, None, f"Gagal membuat arsip zip: {e}"

    @classmethod
    def save_uploaded_file(cls, base_dir: str, filename: str, file_bytes: bytes) -> Tuple[bool, str]:
        """
        Saves uploaded file into WORK_DIR with strict chroot check and automated .bak backup.
        """
        safe_name = Path(filename).name # Strips any path separators
        try:
            target = cls.safe_resolve(base_dir, safe_name)
        except Exception as e:
            return False, f"Akses ditolak: {e}"

        try:
            # Create backup if file already exists
            if target.exists():
                bak_path = target.with_suffix(target.suffix + ".bak")
                shutil.copy2(target, bak_path)
                log.info(f"Created backup for existing file: {bak_path}")

            target.write_bytes(file_bytes)
            size_kb = len(file_bytes) / 1024
            return True, f"File <code>{html.escape(safe_name)}</code> ({size_kb:.1f} KB) berhasil disimpan ke WORK_DIR."
        except Exception as e:
            return False, f"Gagal menyimpan file: {e}"


file_explorer = FileExplorerService()
