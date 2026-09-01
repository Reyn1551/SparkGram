"""
Inline Callback Query Handlers for SparkGram.
Handles session switching, model selection, hardware telemetri, logs viewer, and actions.
"""
import os
import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from ...config import settings
from ...core.session_manager import (
    session_manager,
    build_sessions_html,
    build_sessions_keyboard,
)
from ..middlewares import is_allowed

log = logging.getLogger(__name__)


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispatches button clicks from all inline keyboards."""
    query = update.callback_query
    if not query:
        return

    if not is_allowed(update):
        await query.answer("❌ Akses ditolak. ID kamu tidak terdaftar di whitelist.", show_alert=True)
        return

    data = query.data or ""
    chat_id = update.effective_chat.id if update.effective_chat else 0
    work_dir = session_manager.get_chat_workdir(chat_id)

    # 1. Session Management Callbacks (sw:...)
    if data.startswith("sw:"):
        payload = data[3:]
        
        if payload == "new":
            session_manager.set_active_session(chat_id, None)
            await query.answer("🆕 Session baru disiapkan! Pesan berikutnya akan membuat konteks baru.")
            sessions = await session_manager.fetch_sessions(work_dir=work_dir, limit=30)
            text = build_sessions_html(sessions, None, page=0)
            kb = build_sessions_keyboard(sessions, None, page=0)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif payload == "refresh":
            await query.answer("🔄 Memperbarui daftar sesi...")
            active_id = session_manager.get_active_session(chat_id)
            sessions = await session_manager.fetch_sessions(work_dir=work_dir, limit=30)
            text = build_sessions_html(sessions, active_id, page=0)
            kb = build_sessions_keyboard(sessions, active_id, page=0)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif payload.startswith("page:"):
            try:
                page_num = int(payload.split(":")[1])
            except Exception:
                page_num = 0
            await query.answer(f"Halaman {page_num + 1}")
            active_id = session_manager.get_active_session(chat_id)
            sessions = await session_manager.fetch_sessions(work_dir=work_dir, limit=30)
            text = build_sessions_html(sessions, active_id, page=page_num)
            kb = build_sessions_keyboard(sessions, active_id, page=page_num)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif payload == "workdir":
            await query.answer("📁 Ganti direktori proyek")
            cur_dir = html.escape(session_manager.get_chat_workdir(chat_id))
            text = (
                f"📁 <b>WORK_DIR Proyek Chat Ini:</b>\n"
                f"<code>{cur_dir}</code>\n\n"
                f"Untuk mengganti folder proyek, kirim perintah:\n"
                f"<code>/workdir C:\\Path\\Ke\\Project\\Kamu</code>\n\n"
                f"Atau reset ke default:\n"
                f"<code>/workdir default</code>"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("◀ Kembali ke Sesi", callback_data="sw:refresh")]
            ])
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        else:
            # Switch to specific session_id
            chosen_sid = payload
            session_manager.set_active_session(chat_id, chosen_sid)
            short_id = chosen_sid[-6:] if len(chosen_sid) > 6 else chosen_sid
            await query.answer(f"✅ Switch ke sesi: {short_id}")
            sessions = await session_manager.fetch_sessions(work_dir=work_dir, limit=30)
            text = build_sessions_html(sessions, chosen_sid, page=0)
            kb = build_sessions_keyboard(sessions, chosen_sid, page=0)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

    # 2. Model Switcher Callbacks (mod:...)
    elif data.startswith("mod:"):
        from ...core.models import (
            PRESET_MODELS,
            find_preset_model,
            build_models_html,
            build_models_keyboard,
        )
        mod_id = data[4:].strip()
        matched = find_preset_model(mod_id)
        if matched:
            new_model = matched["model"]
            settings.runtime_model = new_model
            session_manager.save_state()
            await query.answer(f"✅ Model diubah ke: {matched['name']}", show_alert=False)
            text = build_models_html(settings.runtime_model)
            kb = build_models_keyboard(settings.runtime_model)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return
        else:
            await query.answer("❌ Model tidak ditemukan.", show_alert=True)
            return

    # 3. System Health Telemetry Callbacks (hlth:...)
    elif data.startswith("hlth:"):
        payload = data[5:].strip()
        
        if payload == "refresh":
            await query.answer("🔄 Memperbarui telemetri hardware...")
            from ...utils.system_monitor import get_system_health, format_health_html, build_health_keyboard
            active_session = session_manager.get_active_session(chat_id)
            is_busy = chat_id in session_manager.active_tasks and not session_manager.active_tasks[chat_id].done()
            data_health = get_system_health()
            text = format_health_html(data_health, active_session=active_session, is_busy=is_busy)
            kb = build_health_keyboard()
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif payload == "model":
            await query.answer("🤖 Membuka daftar model...")
            from ...core.models import build_models_html, build_models_keyboard
            text = build_models_html(settings.runtime_model)
            kb = build_models_keyboard(settings.runtime_model)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif payload == "logs":
            await query.answer("📜 Mengambil 20 baris log terbaru...")
            from ...utils.log_masker import mask_sensitive_text
            log_file = settings.log_file
            if not log_file.exists():
                await context.bot.send_message(chat_id=chat_id, text="<i>Belum ada log yang tersimpan di disk.</i>", parse_mode=ParseMode.HTML)
                return
            try:
                with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                    all_lines = f.readlines()
                tail = all_lines[-20:]
                raw_text = "".join(tail)
                masked_text = mask_sensitive_text(raw_text)
                if len(masked_text) > 3500:
                    masked_text = masked_text[-3500:]
                escaped = html.escape(masked_text)
                log_msg_text = f"📜 <b>Tail Log Realtime ({len(tail)} baris):</b>\n<pre><code>{escaped}</code></pre>"
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Tutup Pesan Log", callback_data="act:close")]])
                # Send as new message so it never collides with active streaming loop
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=log_msg_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                )
            except Exception as e:
                await context.bot.send_message(chat_id=chat_id, text=f"❌ Gagal membaca log: {html.escape(str(e))}", parse_mode=ParseMode.HTML)
            return

    # 4. Action Button Callbacks (act:...)
    elif data.startswith("act:"):
        payload = data[4:].strip()
        
        if payload == "cancel":
            from ...engine.process_tree import process_supervisor
            cancelled_any = False
            proc = session_manager.active_procs.pop(chat_id, None)
            if proc:
                await process_supervisor.kill_process_tree(proc)
                cancelled_any = True

            task = session_manager.active_tasks.pop(chat_id, None)
            if task and not task.done():
                task.cancel()
                cancelled_any = True

            if cancelled_any:
                await query.answer("🛑 Job dibatalkan.", show_alert=False)
                try:
                    await query.edit_message_text(
                        "🛑 <b>Job berhasil dibatalkan oleh pengguna via tombol.</b>\n<i>Subproses telah dimatikan secara bersih.</i>",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
            else:
                await query.answer("Tidak ada job aktif yang sedang berjalan.", show_alert=True)
            return

        elif payload == "close":
            await query.answer("🗑️ Pesan ditutup.")
            try:
                await query.message.delete()
            except Exception:
                try:
                    await query.edit_message_text("<i>(Pesan ditutup)</i>", parse_mode=ParseMode.HTML)
                except Exception:
                    pass
            return

    # 5. Git Cockpit Callbacks (git:...)
    elif data.startswith("git:"):
        from ...core.git_manager import GitManager
        payload = data[4:].strip()
        gm = GitManager(work_dir)

        if payload == "status":
            await query.answer("🔄 Refreshing status Git...")
            from .commands import build_git_cockpit_ui
            text, kb = await build_git_cockpit_ui(work_dir)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif payload == "stage_all":
            ok, msg = await gm.stage_all()
            await query.answer("➕ Semua file berhasil di-stage!" if ok else f"❌ {msg}", show_alert=not ok)
            from .commands import build_git_cockpit_ui
            text, kb = await build_git_cockpit_ui(work_dir)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif payload == "unstage_all":
            ok, msg = await gm.unstage_all()
            await query.answer("➖ Staged files dikembalikan." if ok else f"❌ {msg}", show_alert=not ok)
            from .commands import build_git_cockpit_ui
            text, kb = await build_git_cockpit_ui(work_dir)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif payload in ("diff_stg", "diff_all"):
            staged_only = (payload == "diff_stg")
            await query.answer("🔍 Memuat diff...")
            ok, diff_text, stats = await gm.get_diff(staged_only=staged_only)
            if not ok or not diff_text:
                await query.answer("Tidak ada diff untuk ditampilkan.", show_alert=True)
                return

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
                [
                    InlineKeyboardButton("📥 Ekspor .patch", callback_data="git:export_patch"),
                    InlineKeyboardButton("✨ AI Commit", callback_data="git:ai_commit"),
                ],
                [InlineKeyboardButton("🌿 Kembali ke Git Cockpit", callback_data="git:status")]
            ])
            try:
                await query.edit_message_text(header + body, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif payload == "ai_commit":
            status = await gm.get_status_summary()
            if not status.get("staged"):
                await gm.stage_all()
                status = await gm.get_status_summary()

            if not status.get("staged"):
                await query.answer("⚠️ Tidak ada perubahan kode untuk di-commit.", show_alert=True)
                return

            commit_msg = gm.generate_ai_commit_message(status)
            await query.answer("✨ Melakukan AI Commit...")
            ok, res = await gm.commit(commit_msg)

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 Push Remote Sekarang", callback_data="git:push")],
                [InlineKeyboardButton("🌿 Kembali ke Git Cockpit", callback_data="git:status")]
            ])
            try:
                await query.edit_message_text(res, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif payload == "push":
            await query.answer("🚀 Melakukan git push...", show_alert=False)
            ok, res = await gm.push()
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🌿 Kembali ke Git Cockpit", callback_data="git:status")]])
            try:
                await query.edit_message_text(res, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif payload == "export_patch":
            import io
            await query.answer("📥 Mengekspor patch...")
            ok, diff_text, _ = await gm.get_diff(staged_only=False)
            if not ok or not diff_text:
                await query.answer("Tidak ada diff untuk diekspor.", show_alert=True)
                return
            patch_bytes = diff_text.encode("utf-8")
            patch_name = f"patch_{int(time.time())}.diff"
            await context.bot.send_document(
                chat_id=chat_id,
                document=io.BytesIO(patch_bytes),
                filename=patch_name,
                caption=f"📝 <b>Git Patch Export:</b> <code>{html.escape(patch_name)}</code>",
                parse_mode=ParseMode.HTML,
            )
            return

    # 3b. Memory Callbacks (mem:...)
    elif data.startswith("mem:"):
        from ...memory.manager import memory_manager
        payload = data[4:].strip()
        if payload == "recent":
            await query.answer("🧠 Memuat memory terbaru...")
            recent = memory_manager.recent(days=7, limit=20)
            stats = memory_manager.stats()
            if not recent:
                text = f"🧠 <b>Persistent Memory</b> — {stats['files']} file(s)\n<i>Belum ada memory.</i>"
            else:
                inner = "\n".join(html.escape(l) for l in recent)
                text = f"🧠 <b>Persistent Memory</b> — {stats['files']} file(s), {stats['lines']} baris\n<blockquote expandable>\n{inner}\n</blockquote>"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔍 Search", callback_data="mem:search"), InlineKeyboardButton("🗑️ Cleanup", callback_data="mem:cleanup")]])
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return
        elif payload == "search":
            await query.answer("Ketik /memory kata_kunci untuk search")
            await context.bot.send_message(chat_id=chat_id, text="🔍 <b>Memory Search:</b>\nKirim <code>/memory kata_kunci</code> untuk cari memory.\nContoh: <code>/memory refactor</code>", parse_mode=ParseMode.HTML)
            return
        elif payload == "cleanup":
            deleted = memory_manager.cleanup(keep_days=30)
            await query.answer(f"🗑️ {deleted} file lama dihapus" if deleted else "Tidak ada file lama", show_alert=True)
            return

    # 6. Developer Macro Callbacks (macro:...)
    elif data.startswith("macro:"):
        payload = data[6:].strip()
        if payload.startswith("run:"):
            recipe_id = payload[4:]
            await query.answer(f"🚀 Menjalankan resep /{recipe_id}...")
            from .commands import _dispatch_macro
            await _dispatch_macro(update, context, recipe_id)
            return

    # 7. File Explorer Callbacks (fe:...)
    elif data.startswith("fe:"):
        from ...engine.file_explorer import file_explorer, state_cache
        payload = data[3:].strip()
        parts = payload.split(":")
        action = parts[0]
        token = parts[1] if len(parts) > 1 else ""

        if action == "noop":
            await query.answer()
            return

        rel_path = state_cache.get_path(token) or ""

        if action == "cd":
            await query.answer("📁 Beralih folder...")
            text, kb = file_explorer.build_file_tree_ui(base_dir=work_dir, current_subpath=rel_path, page=0)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif action == "rf":
            await query.answer("🔄 Memperbarui direktori...")
            text, kb = file_explorer.build_file_tree_ui(base_dir=work_dir, current_subpath=rel_path, page=0)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif action == "p":
            page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
            await query.answer()
            text, kb = file_explorer.build_file_tree_ui(base_dir=work_dir, current_subpath=rel_path, page=page)
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif action == "vw":
            await query.answer("📄 Membaca file...")
            ok, content = file_explorer.read_file_preview(base_dir=work_dir, rel_path=rel_path)
            parent_rel = str(Path(rel_path).parent).replace("\\", "/") if "/" in rel_path else "."
            parent_token = state_cache.register_path(parent_rel)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 Unduh File", callback_data=f"fe:dl:{token}")],
                [InlineKeyboardButton("◀ Kembali ke Folder", callback_data=f"fe:cd:{parent_token}")]
            ])
            try:
                await query.edit_message_text(content, parse_mode=ParseMode.HTML, reply_markup=kb if ok else None)
            except Exception:
                pass
            return

        elif action == "dl":
            await query.answer("📥 Mengunduh file...")
            try:
                target = file_explorer.safe_resolve(work_dir, rel_path)
                if target.is_file():
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=open(target, "rb"),
                        filename=target.name,
                        caption=f"📄 <code>{html.escape(target.name)}</code>",
                        parse_mode=ParseMode.HTML,
                    )
            except Exception as e:
                await query.answer(f"Gagal mengunduh: {e}", show_alert=True)
            return

        elif action == "zip":
            await query.answer("📦 Mengompresi folder zip...")
            ok, zip_bytes, zip_name = file_explorer.create_safe_zip(base_dir=work_dir, rel_path=rel_path)
            if ok and zip_bytes:
                import io
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=io.BytesIO(zip_bytes),
                    filename=zip_name,
                    caption=f"📦 Arsip Zip: <code>{html.escape(zip_name)}</code>",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await query.answer(f"Gagal membuat zip: {zip_name}", show_alert=True)
            return

    # 8. Visual Web UI Preview Callbacks (pw:...)
    elif data.startswith("pw:"):
        from ...engine.playwright_preview import playwright_preview
        from ...engine.file_explorer import state_cache
        import io
        import time
        payload = data[3:].strip()
        parts = payload.split(":")
        action = parts[0]
        token = parts[1] if len(parts) > 1 else ""
        target = state_cache.get_path(token) or token or "3000"
        preset = parts[2] if len(parts) > 2 else "desktop"

        if action in ("vw", "rf"):
            await query.answer(f"📸 Memuat snapshot ({preset})...")
            ok, img_bytes, meta = await playwright_preview.capture_url(
                url_or_port=target,
                viewport_type=preset,
            )
            if not ok or not img_bytes:
                await query.answer(f"Gagal snapshot: {meta.get('error')}", show_alert=True)
                return

            url = meta.get("url", target)
            render_time = meta.get("render_time_ms", 0)
            status_code = meta.get("status", 200)
            v_name = meta.get("viewport_name", preset)

            caption = (
                f"📸 <b>Web Preview:</b> <code>{html.escape(url)}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🌐 Status: <code>{status_code}</code> • ⏱️ Render: <code>{render_time}ms</code>\n"
                f"📐 Viewport: <b>{v_name}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )

            other_preset = "mobile" if preset == "desktop" else "desktop"
            other_label = "📱 Mobile (390px)" if preset == "desktop" else "💻 Desktop (1440p)"

            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(other_label, callback_data=f"pw:vw:{token}:{other_preset}"),
                    InlineKeyboardButton("🔄 Refresh", callback_data=f"pw:rf:{token}:{preset}"),
                ],
                [
                    InlineKeyboardButton("📜 Console Logs", callback_data=f"pw:log:{token}"),
                    InlineKeyboardButton("📥 Unduh HD", callback_data=f"pw:hd:{token}:{preset}"),
                ],
                [InlineKeyboardButton("🗑️ Tutup", callback_data="act:close")]
            ])

            from telegram import InputMediaPhoto
            try:
                await query.edit_message_media(
                    media=InputMediaPhoto(media=io.BytesIO(img_bytes), caption=caption, parse_mode=ParseMode.HTML),
                    reply_markup=kb,
                )
            except Exception:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=io.BytesIO(img_bytes),
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                )
            return

        elif action == "log":
            await query.answer("📜 Membaca log konsol browser...")
            valid_url = f"http://localhost:{target}" if target.isdigit() else target
            logs = playwright_preview.get_console_logs(valid_url)
            if not logs:
                logs_text = "✨ <i>Tidak ada pesan log/error di konsol browser.</i>"
            else:
                formatted = "\n".join(logs[-25:])
                logs_text = f"📜 <b>Console Logs ({len(logs)} pesan):</b>\n<blockquote expandable><pre><code>{html.escape(formatted)}</code></pre></blockquote>"

            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Tutup Log", callback_data="act:close")]])
            await context.bot.send_message(
                chat_id=chat_id,
                text=logs_text,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
            return

        elif action == "hd":
            await query.answer("📥 Mengirim gambar resolusi HD...")
            ok, img_bytes, meta = await playwright_preview.capture_url(
                url_or_port=target,
                viewport_type=preset,
            )
            if ok and img_bytes:
                filename = f"preview_{preset}_{int(time.time())}.jpg"
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=io.BytesIO(img_bytes),
                    filename=filename,
                    caption=f"📸 <b>Snapshot HD ({preset}):</b> <code>{html.escape(meta.get('url', target))}</code>",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await query.answer("Gagal mengambil gambar HD.", show_alert=True)
            return

    # 9. Port Management Callbacks (port:...)
    elif data.startswith("port:"):
        from ...engine.port_manager import port_manager
        payload = data[5:].strip()

        if payload == "list":
            await query.answer("🔄 Refreshing ports...")
            text, kb = port_manager.build_ports_ui()
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            return

        elif payload.startswith("kill:"):
            port_str = payload[5:]
            if port_str.isdigit():
                port_num = int(port_str)
                ok, msg, _ = port_manager.kill_port(port_num)
                await query.answer("🛑 Port dimatikan!" if ok else "❌ Gagal mematikan port", show_alert=True)
                text, kb = port_manager.build_ports_ui()
                try:
                    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
                except Exception:
                    pass
            return

    await query.answer()
