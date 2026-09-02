"""
Macro Manager and Developer Recipe Hub for SparkGram.
Provides prompt templates with automated repository context injection (git diff, file content).
"""
import os
import html
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

log = logging.getLogger(__name__)

RECIPES: Dict[str, Dict[str, Any]] = {
    "review": {
        "name": "Code Review (Git Diff)",
        "emoji": "🔍",
        "description": "Audit security, concurrency race conditions, memory leaks, and edge-cases pada git diff staged.",
        "template": (
            "Lakukan review kode mendalam dan teliti terhadap perubahan kode berikut.\n\n"
            "Fokus analisis:\n"
            "1. Celah keamanan (OWASP, injection, unhandled error, secret leak)\n"
            "2. Concurrency & Race conditions (deadlock, pipe saturation, async cancellation)\n"
            "3. Efisiensi & Clean Code (kompleksitas, standard library)\n\n"
            "Format output:\n"
            "• [CRITICAL / SEVERITY HIGH] jika ada bug berbahaya\n"
            "• [WARNING / PERBAIKAN] saran optimasi konkret\n"
            "• [REKOMENDASI KODE] cuplikan perbaikan siap pakai\n\n"
            "=== PERUBAHAN KODE (DIFF) ===\n{context}\n"
        ),
        "requires_context": "git_diff",
    },
    "testgen": {
        "name": "Unit Test Generator (pytest)",
        "emoji": "🧪",
        "description": "Otomatis membuat test suite pytest komprehensif lengkap dengan edge-cases & mock.",
        "template": (
            "Buatkan automated unit test suite lengkap menggunakan pytest untuk target berikut.\n\n"
            "Target: {target}\n\n"
            "Persyaratan test:\n"
            "1. Cakup happy path, edge cases (input kosong, null, tipe salah), dan error paths.\n"
            "2. Gunakan fixture dan mocking bersih jika ada I/O atau network.\n"
            "3. Pastikan test independen, idempotent, dan 100% lulus.\n\n"
            "=== KODE SUMBER ===\n{context}\n"
        ),
        "requires_context": "file_content",
    },
    "explain": {
        "name": "Deep Code Tracing",
        "emoji": "⚡",
        "description": "Jelaskan arsitektur, dependensi, data flow, dan alur eksekusi file/fungsi.",
        "template": (
            "Jelaskan arsitektur, alur data (data flow), dan logika kerja dari target berikut secara tajam, lugas, dan terstruktur.\n\n"
            "Target: {target}\n\n"
            "=== KODE SUMBER ===\n{context}\n"
        ),
        "requires_context": "file_content",
    },
    "refactor": {
        "name": "Clean Code & Performance Refactor",
        "emoji": "🧹",
        "description": "Refactor modul untuk meningkatkan readability & efisiensi tanpa mengubah perilaku publik.",
        "template": (
            "Lakukan refactoring pada target berikut dengan standar Clean Architecture & high performance.\n\n"
            "Target: {target}\n"
            "Instruksi tambahan: {instruction}\n\n"
            "Persyaratan:\n"
            "1. Jaga backward compatibility interface publik.\n"
            "2. Eliminasi boilerplate dan duplikasi logika.\n"
            "3. Sediakan kode akhir yang utuh dan siap jalan.\n\n"
            "=== KODE SUMBER ===\n{context}\n"
        ),
        "requires_context": "file_content",
    },
    "doc": {
        "name": "API & Markdown Documentation",
        "emoji": "📝",
        "description": "Buat dokumentasi API teknis, tipe data, dan contoh penggunaan praktis.",
        "template": (
            "Buatkan dokumentasi teknis yang humanis, akurat, dan bebas AI-slop untuk modul berikut.\n\n"
            "Target: {target}\n\n"
            "=== KODE SUMBER ===\n{context}\n"
        ),
        "requires_context": "file_content",
    },
}


class MacroManager:
    """Manages prompt recipe templates and context injection."""

    @staticmethod
    def list_recipes() -> List[Dict[str, Any]]:
        """Returns list of available recipes with metadata."""
        res = []
        for key, val in RECIPES.items():
            res.append({
                "id": key,
                "name": val["name"],
                "emoji": val["emoji"],
                "description": val["description"],
            })
        return res

    @staticmethod
    def get_recipe(recipe_id: str) -> Optional[Dict[str, Any]]:
        return RECIPES.get(recipe_id.lower())

    @classmethod
    async def build_macro_prompt(
        cls,
        recipe_id: str,
        work_dir: str,
        target: str = "",
        instruction: str = "",
    ) -> Tuple[bool, str, str]:
        """
        Builds complete AI prompt by assembling template and local repo context.
        Returns (success, prompt_or_error, summary_title).
        """
        recipe = cls.get_recipe(recipe_id)
        if not recipe:
            return False, f"Resep <code>{html.escape(recipe_id)}</code> tidak ditemukan.", ""

        context_data = ""
        req = recipe.get("requires_context")

        if req == "git_diff":
            from .git_manager import GitManager
            gm = GitManager(work_dir)
            ok, diff_text, _ = await gm.get_diff(staged_only=True)
            if not ok or not diff_text:
                # Fallback to unstaged diff
                ok, diff_text, _ = await gm.get_diff(staged_only=False)
            if not diff_text:
                return False, "⚠️ Tidak ada perubahan kode (git diff) di repositori aktif untuk di-review.", ""
            context_data = diff_text[:12000] # Limit context size

        elif req == "file_content":
            if not target:
                return False, f"⚠️ Resep <code>{recipe_id}</code> memerlukan argumen nama file. Contoh: <code>/{recipe_id} sparkgram/config.py</code>", ""
            
            target_path = (Path(work_dir) / target).resolve()
            if not target_path.exists() or not target_path.is_file():
                return False, f"⚠️ File <code>{html.escape(target)}</code> tidak ditemukan di WORK_DIR.", ""
            
            try:
                content = target_path.read_text(encoding="utf-8", errors="replace")
                context_data = content[:15000]
            except Exception as e:
                return False, f"Gagal membaca file: {e}", ""

        # Format final prompt
        rendered = recipe["template"].format(
            target=target or "Current Workspace",
            instruction=instruction or "Optimalkan secara menyeluruh",
            context=context_data or "(Tidak ada konteks tambahan)",
        )
        title = f"{recipe['emoji']} {recipe['name']}"
        return True, rendered, title


macro_manager = MacroManager()
