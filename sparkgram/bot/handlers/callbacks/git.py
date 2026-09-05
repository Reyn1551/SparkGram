"""Git callbacks (git:) — extracted from callbacks.py"""
import html
import time
import io
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from ....core.git_manager import GitManager


async def handle(query, context, chat_id: int, work_dir: str, payload: str) -> bool:
    payload = payload.strip()
    gm = GitManager(work_dir)

    if payload == "status":
        await query.answer("🔄 Refreshing status Git...")
        from ..git import build_git_cockpit_ui
        text, kb = await build_git_cockpit_ui(work_dir)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if payload == "stage_all":
        ok, msg = await gm.stage_all()
        await query.answer("➕ Semua file berhasil di-stage!" if ok else f"❌ {msg}", show_alert=not ok)
        from ..git import build_git_cockpit_ui
        text, kb = await build_git_cockpit_ui(work_dir)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if payload == "unstage_all":
        ok, msg = await gm.unstage_all()
        await query.answer("➖ Staged files dikembalikan." if ok else f"❌ {msg}", show_alert=not ok)
        from ..git import build_git_cockpit_ui
        text, kb = await build_git_cockpit_ui(work_dir)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if payload in ("diff_stg", "diff_all"):
        staged_only = (payload == "diff_stg")
        await query.answer("🔍 Memuat diff...")
        ok, diff_text, stats = await gm.get_diff(staged_only=staged_only)
        if not ok or not diff_text:
            await query.answer("Tidak ada diff untuk ditampilkan.", show_alert=True)
            return True
        mode_label = "Staged" if staged_only else "All Working Tree"
        header = (
            f"📝 <b>Git Diff ({mode_label})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🟢 <b>+{stats['added']}</b> Baris   🔴 <b>-{stats['deleted']}</b> Baris   📁 <b>{stats['files_count']}</b> Berkas\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        if len(diff_text) > 3200:
            truncated = diff_text[:3200] + "\n\n... (diff terpotong — gunakan tombol Ekspor .patch)"
            body = f"<blockquote expandable><pre><code class=\"language-diff\">{html.escape(truncated)}</code></pre></blockquote>"
        else:
            body = f"<blockquote expandable><pre><code class=\"language-diff\">{html.escape(diff_text)}</code></pre></blockquote>"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Ekspor .patch", callback_data="git:export_patch"), InlineKeyboardButton("✨ AI Commit", callback_data="git:ai_commit")],
            [InlineKeyboardButton("🌿 Kembali ke Git Cockpit", callback_data="git:status")]
        ])
        try:
            await query.edit_message_text(header + body, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if payload == "ai_commit":
        status = await gm.get_status_summary()
        if not status.get("staged"):
            await gm.stage_all()
            status = await gm.get_status_summary()
        if not status.get("staged"):
            await query.answer("⚠️ Tidak ada perubahan kode untuk di-commit.", show_alert=True)
            return True
        commit_msg = gm.generate_ai_commit_message(status)
        await query.answer("✨ Melakukan AI Commit...")
        ok, res = await gm.commit(commit_msg)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Push Remote Sekarang", callback_data="git:push")], [InlineKeyboardButton("🌿 Kembali ke Git Cockpit", callback_data="git:status")]])
        try:
            await query.edit_message_text(res, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if payload == "push":
        await query.answer("🚀 Melakukan git push...", show_alert=False)
        ok, res = await gm.push()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🌿 Kembali ke Git Cockpit", callback_data="git:status")]])
        try:
            await query.edit_message_text(res, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if payload == "export_patch":
        await query.answer("📥 Mengekspor patch...")
        ok, diff_text, _ = await gm.get_diff(staged_only=False)
        if not ok or not diff_text:
            await query.answer("Tidak ada diff untuk diekspor.", show_alert=True)
            return True
        patch_bytes = diff_text.encode("utf-8")
        patch_name = f"patch_{int(time.time())}.diff"
        await context.bot.send_document(chat_id=chat_id, document=io.BytesIO(patch_bytes), filename=patch_name, caption=f"📝 <b>Git Patch Export:</b> <code>{html.escape(patch_name)}</code>", parse_mode=ParseMode.HTML)
        return True

    return False
