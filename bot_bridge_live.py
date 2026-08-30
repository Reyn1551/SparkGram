"""
Telegram -> AI LIVE Bridge — PnP (Plug-and-Play) ke model & metode apa aja
- Live loading: edit pesan tiap detik, bukan nunggu buta
- Output cantik: Markdown -> Telegram HTML (bukan raw .md)
- PnP model: MODEL dari env (.env) — opencode/*, groq/*, deepseek/*, dll — ganti tanpa restart via /model
- PnP metode: polling (dev) vs webhook (prod) auto-switch via WEBHOOK_URL
- PnP setup: git clone anywhere → cp .env.example .env → docker compose up
Default: opencode/muse-spark-1.2-contributor-free (gratis), tapi PnP ke model apa aja.
"""
import asyncio
import html
import json
import logging
import os
import re
import time
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# === KONFIG PnP — semua dari env biar git clone anywhere ===
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8808398800:AAGG9aG3iupOpurz-lqJ7LghZC0-M2f9tsQ")
ALLOWED_USER_IDS = {int(x.strip()) for x in os.getenv("ALLOWED_USER_IDS", "1925430810").split(",") if x.strip().isdigit()}
WORK_DIR = os.getenv("WORK_DIR", str(Path(__file__).parent.resolve()))  # GANTI via .env: r"D:\Riset\HyperSpectral"
# PnP model: set via .env MODEL atau /model di Telegram — default muse-spark gratis
MODEL = os.getenv("MODEL", os.getenv("OPENCODE_MODEL", "opencode/muse-spark-1.2-contributor-free"))
# PnP metode: kosong = polling (dev), isi = webhook prod (https://your-app.up.railway.app/webhook)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
PORT = int(os.getenv("PORT", "8000"))
TIMEOUT_SECONDS = int(os.getenv("TIMEOUT_SECONDS", "300"))
# Runtime model override per-process (via /model set)
RUNTIME_MODEL = MODEL

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# ====== TELEGRAM HTML FORMATTER ======
def md_to_telegram_html(md: str) -> str:
    """Convert Markdown opencode -> Telegram HTML yang cantik."""
    if not md:
        return ""

    # 1. Simpan code block & inline code dulu biar tidak diproses markdown lain
    code_blocks = []
    def save_codeblock(m):
        lang = (m.group(1) or "").strip()
        code = m.group(2)
        code_esc = html.escape(code)
        # Telegram <pre> support language hint via <pre><code class="">
        # Simpler: <pre>code</pre> atau <pre language="python">
        if lang:
            # Telegram HTML tidak support class, tapi <pre> saja cukup
            replaced = f"<pre>{code_esc}</pre>"
        else:
            replaced = f"<pre>{code_esc}</pre>"
        code_blocks.append(replaced)
        return f"@@CODEBLOCK{len(code_blocks)-1}@@"

    # ```lang\ncode\n```
    md = re.sub(r"```(\w+)?\n(.*?)```", save_codeblock, md, flags=re.DOTALL)
    # ```code``` single line without \n
    md = re.sub(r"```(.*?)```", lambda m: save_codeblock(re.match(r"```(\w+)?\n(.*?)```", "```\n"+m.group(1)+"\n```", re.DOTALL) or m), md, flags=re.DOTALL)

    inline_codes = []
    def save_inline(m):
        code_esc = html.escape(m.group(1))
        inline_codes.append(f"<code>{code_esc}</code>")
        return f"@@INLINE{len(inline_codes)-1}@@"
    md = re.sub(r"`([^`]+?)`", save_inline, md)

    # 2. Escape HTML sisa (di luar placeholder)
    # Kita escape dulu, lalu restore placeholder yang sudah jadi tag HTML
    # Jadi escape bagian yang bukan placeholder
    # Cara aman: escape seluruh md, lalu kembalikan placeholder
    md_escaped = html.escape(md)

    # 3. Markdown -> HTML (setelah escape, karakter markdown * _ [ masih ada karena tidak di-escape)
    # Bold **text** atau __text__
    md_escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", md_escaped)
    md_escaped = re.sub(r"__(.+?)__", r"<b>\1</b>", md_escaped)
    # Italic *text* atau _text_ (hati-hati jangan greedy)
    # Gunakan negative lookahead agar tidak makan **
    md_escaped = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", md_escaped)
    md_escaped = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", md_escaped)
    # Strikethrough ~~text~~
    md_escaped = re.sub(r"~~(.+?)~~", r"<s>\1</s>", md_escaped)
    # Link [text](url)
    md_escaped = re.sub(r"\[([^\]]+?)\]\((https?://[^)]+?)\)", r'<a href="\2">\1</a>', md_escaped)
    # Heading # ## ### -> <b>
    md_escaped = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", md_escaped, flags=re.MULTILINE)
    # Bullet - atau * di awal baris -> •
    md_escaped = re.sub(r"^\s*[-*]\s+", "• ", md_escaped, flags=re.MULTILINE)
    # Numbered list tetap
    # Persamaan LaTeX $...$ -> <i> biar miring, atau <code>
    # Biarkan sebagai <i> agar tidak hilang
    md_escaped = re.sub(r"\$(.+?)\$", r"<i>\1</i>", md_escaped)

    # 4. Restore code placeholders (sudah HTML)
    for i, block in enumerate(code_blocks):
        md_escaped = md_escaped.replace(f"@@CODEBLOCK{i}@@", block)
    for i, code in enumerate(inline_codes):
        md_escaped = md_escaped.replace(f"@@INLINE{i}@@", code)

    # 5. Bersihkan baris kosong berlebihan
    md_escaped = re.sub(r"\n{3,}", "\n\n", md_escaped)
    return md_escaped.strip()


def split_html(text_html: str, limit: int = 3800):
    """Split Telegram HTML aman — JANGAN potong di dalam <pre>/<code>.
    Fallback: kalau terpaksa, potong di \n\n terdekat sebelum limit."""
    if len(text_html) <= limit:
        yield text_html
        return
    start = 0
    n = len(text_html)
    while start < n:
        end = min(start + limit, n)
        if end >= n:
            yield text_html[start:end]
            break
        # Hindari potong di dalam tag <pre>...</pre> atau <code>...</code>
        # Cari posisi aman: cari \n\n terdekat SEBELUM end yang tidak di dalam tag
        # Sederhana: mundur sampai ketemu \n\n dan cek apakah di dalam <pre>/<code>
        safe_end = end
        # Cek apakah kita di dalam <pre> atau <code> dengan hitung tag buka/tutup
        segment = text_html[start:end]
        # Hitung tag yang belum tertutup di segment
        open_pre = segment.count("<pre>") - segment.count("</pre>")
        open_code = segment.count("<code>") - segment.count("</code>")
        if open_pre > 0 or open_code > 0:
            # Cari tutup tag terdekat setelah end (dalam window 500 char)
            close_pre = text_html.find("</pre>", end)
            close_code = text_html.find("</code>", end)
            candidates = [c for c in [close_pre, close_code] if c != -1]
            if candidates:
                safe_end = min(candidates) + (7 if min(candidates) == close_pre else 7)  # len("</pre>")==6, "</code>"==7
                # clamp
                safe_end = min(safe_end, start + limit + 800)
            else:
                # fallback: cari \n\n sebelum end
                cut = text_html.rfind("\n\n", start, end)
                if cut != -1 and cut > start + 500:
                    safe_end = cut + 2
        else:
            cut = text_html.rfind("\n\n", start, end)
            if cut != -1 and cut > start + 500:
                safe_end = cut + 2

        # Pastikan tidak melebihi limit terlalu jauh dan tidak infinite loop
        if safe_end <= start:
            safe_end = end
        yield text_html[start:safe_end]
        start = safe_end


def split_markdown(md: str, header_html: str, limit: int = 3500):
    """Split MARKDOWN dulu baru convert ke HTML — tiap chunk jadi HTML valid (fix stuck 42s)."""
    # Split markdown di batas paragraf \n\n agar tidak potong code block di tengah
    if not md:
        return [header_html] if header_html else []
    # Estimasi: 1 char md ~ 1.1 char html, jadi pakai limit 3000 untuk md
    md_limit = 3000
    chunks_md = []
    start = 0
    while start < len(md):
        end = min(start + md_limit, len(md))
        if end < len(md):
            # jangan potong di dalam ``` code block
            # Hitung apakah kita di dalam code block (jumlah ``` ganjil)
            segment = md[start:end]
            open_blocks = segment.count("```") % 2
            if open_blocks == 1:
                close = md.find("```", end)
                if close != -1 and close < start + md_limit + 2000:
                    end = close + 3
                else:
                    # fallback cari \n\n
                    cut = md.rfind("\n\n", start, end)
                    if cut != -1 and cut > start + 500:
                        end = cut + 2
            else:
                cut = md.rfind("\n\n", start, end)
                if cut != -1 and cut > start + 500:
                    end = cut + 2
        chunks_md.append(md[start:end])
        start = end

    html_chunks = []
    for i, c in enumerate(chunks_md):
        body_html = md_to_telegram_html(c)
        if i == 0:
            full = f"{header_html}\n\n{body_html}" if header_html else body_html
        else:
            full = body_html
        # Jika full masih >3800 (misal code block panjang), split lagi via split_html
        if len(full) > 3800:
            for sub in split_html(full, 3800):
                html_chunks.append(sub)
        else:
            html_chunks.append(full)
    return html_chunks


def is_allowed(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else None
    return uid in ALLOWED_USER_IDS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    mode = "webhook" if WEBHOOK_URL else "polling"
    await update.message.reply_text(
        f"✨ <b>Live Bridge PnP Aktif</b> • <code>{html.escape(RUNTIME_MODEL)}</code>\n\n"
        f"WORK_DIR: <code>{html.escape(WORK_DIR)}</code>\n"
        f"Mode: <code>{mode}</code> {'('+html.escape(WEBHOOK_URL)+')' if WEBHOOK_URL else '(dev, laptop harus nyala)'}\n"
        f"Model PnP: <code>{html.escape(RUNTIME_MODEL)}</code>\n\n"
        f"Kirim prompt natural, aku streaming langsung — bukan nunggu buta.\n"
        f"Contoh: <i>buatkan file hello.py print halo dunia</i>\n\n"
        f"Perintah PnP:\n"
        f"/model - lihat & ganti model\n"
        f"/model list - daftar model populer\n"
        f"/model set groq/llama-3.3-70b-versatile - ganti model\n"
        f"/id - chat_id\n"
        f"/pwd - WORK_DIR\n"
        f"/help - bantuan",
        parse_mode=ParseMode.HTML,
    )


async def model_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global RUNTIME_MODEL
    args = context.args or []
    if not args:
        await update.message.reply_text(
            f"🤖 Model aktif: <code>{html.escape(RUNTIME_MODEL)}</code>\n"
            f"Env MODEL: <code>{html.escape(MODEL)}</code>\n"
            f"WORK_DIR: <code>{html.escape(WORK_DIR)}</code>\n\n"
            f"PnP — ganti model tanpa restart:\n"
            f"<code>/model set opencode/muse-spark-1.2-contributor-free</code>\n"
            f"<code>/model set groq/llama-3.3-70b-versatile</code>\n"
            f"<code>/model set deepseek/deepseek-v4-flash</code>\n"
            f"<code>/model set openai/gpt-4o-mini</code>\n\n"
            f"List: <code>/model list</code> atau <code>opencode models</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    if args[0] == "list":
        popular = [
            "opencode/muse-spark-1.2-contributor-free (gratis, default)",
            "opencode/big-pickle",
            "groq/llama-3.3-70b-versatile (cepat, gratis tier)",
            "groq/openai/gpt-oss-120b",
            "deepseek/deepseek-v4-flash",
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
        ]
        await update.message.reply_text(
            "📋 <b>Model populer (PnP):</b>\n" + "\n".join(f"• <code>{html.escape(m)}</code>" for m in popular) +
            "\n\nGanti: <code>/model set &lt;nama&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    if args[0] == "set" and len(args) >= 2:
        if not is_allowed(update):
            await update.message.reply_text("Akses ditolak.")
            return
        new_model = args[1].strip()
        # validasi sederhana: harus ada /
        if "/" not in new_model:
            await update.message.reply_text("Format: <code>provider/model</code> contoh <code>groq/llama-3.3-70b-versatile</code>", parse_mode=ParseMode.HTML)
            return
        RUNTIME_MODEL = new_model
        await update.message.reply_text(
            f"✅ Model diganti → <code>{html.escape(RUNTIME_MODEL)}</code>\n"
            f"Berlaku untuk semua prompt selanjutnya (runtime, restart kembali ke env MODEL).",
            parse_mode=ParseMode.HTML,
        )
        log.info(f"MODEL switched to {RUNTIME_MODEL} by {update.effective_user.id}")
        return
    await update.message.reply_text("Gunakan: <code>/model</code>, <code>/model list</code>, <code>/model set provider/model</code>", parse_mode=ParseMode.HTML)


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"chat_id: <code>{update.effective_chat.id}</code>\nuser_id: <code>{update.effective_user.id}</code>",
        parse_mode=ParseMode.HTML,
    )


async def pwd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"WORK_DIR: <code>{html.escape(WORK_DIR)}</code>", parse_mode=ParseMode.HTML)


# ===== LIVE STREAMING CORE =====
async def stream_opencode(prompt: str, status_msg, bot, chat_id: int):
    """
    Jalankan opencode run --format json dan streaming step-by-step ke Telegram via edit.
    Return: (final_text, tool_logs, elapsed, tokens)
    """
    cmd = [
        "opencode", "run", prompt,
        "--dir", WORK_DIR,
        "--format", "json",
        "--model", RUNTIME_MODEL,
        "--auto",
        "--thinking",  # agar dapat reasoning event untuk live indicator
    ]
    log.info(f"STREAM PnP: model={RUNTIME_MODEL} dir={WORK_DIR} | {' '.join(cmd)}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=10 * 1024 * 1024,  # 10 MB — cegah LimitOverrunError untuk JSON line raksasa
    )

    assistant_text = ""
    tool_logs = []
    reasoning_active = False
    start_time = time.time()
    last_text_len = 0
    tokens_info = {}

    # Shared throttle dict dipakai animate + throttled_edit
    shared = {"last_edit": 0}

    # Task animasi loading tiap 1s kalau belum ada update
    async def animate():
        dots = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        idx = 0
        while True:
            await asyncio.sleep(1.0)
            if proc.returncode is not None:
                break
            elapsed = int(time.time() - start_time)
            if time.time() - shared["last_edit"] < 1.0:
                continue
            spinner = dots[idx % len(dots)]
            idx += 1
            short_model = RUNTIME_MODEL.split("/")[-1][:18]
            if reasoning_active and not assistant_text:
                text = f"{spinner} <b>{html.escape(short_model)} berpikir...</b> {elapsed}s\n<code>{html.escape(prompt[:60])}</code>"
            elif tool_logs and not assistant_text:
                last_tool = tool_logs[-1]
                text = f"{spinner} <b>{html.escape(short_model)} mengerjakan...</b> {elapsed}s\n{last_tool}\n<code>{html.escape(prompt[:60])}</code>"
            elif assistant_text:
                preview_md = assistant_text[-1200:]
                html_preview = md_to_telegram_html(preview_md)
                if len(html_preview) > 1500:
                    preview_md = assistant_text[-800:]
                    html_preview = "…" + md_to_telegram_html(preview_md)
                text = f"{spinner} <b>{html.escape(short_model)} menulis...</b> {elapsed}s\n{html_preview}"
            else:
                text = f"{spinner} <b>{html.escape(short_model)} memproses...</b> {elapsed}s\n<code>{html.escape(prompt[:60])}</code>"
            try:
                await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
                shared["last_edit"] = time.time()
            except Exception as e:
                log.debug(f"animate edit skip: {e}")

    anim_task = asyncio.create_task(animate())

    async def throttled_edit(html_text: str):
        now = time.time()
        if now - shared["last_edit"] < 1.1:
            return
        shared["last_edit"] = now
        try:
            await status_msg.edit_text(html_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            msg = str(e).lower()
            if "too long" in msg or "can't parse entities" in msg or "can't find end tag" in msg:
                # Fallback: coba potong aman atau kirim plain tanpa HTML
                try:
                    # coba fallback plain text tanpa parse_mode
                    plain = re.sub(r"<[^>]+>", "", html_text)
                    await status_msg.edit_text(plain[:3800] + "…")
                except:
                    try:
                        await status_msg.edit_text(html_text[:3800] + "…", parse_mode=ParseMode.HTML)
                    except:
                        pass
            else:
                log.debug(f"edit skip: {e}")

    try:
        # Baca stdout baris per baris (JSON per baris) — robust untuk line raksasa (>64KB)
        # readline() default limit 64KB bisa jebol LimitOverrunError, jadi pakai chunked read
        buf = b""
        async def iter_lines(reader):
            nonlocal buf
            while True:
                chunk = await reader.read(8192)
                if not chunk:
                    if buf.strip():
                        yield buf
                        buf = b""
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    yield line

        async for raw_line in iter_lines(proc.stdout):
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except:
                continue

            etype = event.get("type")
            part = event.get("part", {})

            if etype == "reasoning":
                reasoning_active = True
                # reasoning punya encrypted content, kita tampilkan indikator saja
                elapsed = int(time.time() - start_time)
                short_model = RUNTIME_MODEL.split("/")[-1]
                html_text = f"💭 <b>{html.escape(short_model)} berpikir...</b> {elapsed}s\n<code>{html.escape(prompt[:80])}</code>\n<i>reasoning {elapsed}s • {html.escape(RUNTIME_MODEL)}</i>"
                await throttled_edit(html_text)

            elif etype == "text":
                txt = part.get("text", "")
                if txt:
                    # kadang text datang sebagai potongan, kita akumulasi
                    # cek apakah ini lanjutan atau baru: opencode kirim full per step, bukan delta
                    # Jika text sudah ada di assistant_text (duplikat), jangan append double
                    # Simpler: kalau panjang txt < 500 dan assistant_text endswith txt -> skip?
                    # Tapi test sebelumnya: tiap step text berbeda, jadi aman append dengan \n jika sudah ada
                    if assistant_text and not assistant_text.endswith("\n") and not txt.startswith("\n"):
                        assistant_text += "\n\n"
                    assistant_text += txt
                    reasoning_active = False

                    elapsed = int(time.time() - start_time)
                    # FIX: potong markdown dulu, jangan potong HTML (cegah broken tag)
                    preview_md = assistant_text[-3000:] if len(assistant_text) > 3000 else assistant_text
                    if len(assistant_text) > 3000:
                        preview_md = "…\n" + preview_md
                    html_body = md_to_telegram_html(preview_md)
                    short_model = RUNTIME_MODEL.split("/")[-1]
                    html_text = f"✍️ <b>{html.escape(short_model)}</b> • {elapsed}s\n{html_body}"
                    await throttled_edit(html_text)
                    await bot.send_chat_action(chat_id=chat_id, action="typing")

            elif etype == "tool_use":
                tool = part.get("tool", "tool")
                title = part.get("title") or part.get("state", {}).get("metadata", {}).get("filepath", "") or ""
                # shorten title
                short = title.replace(WORK_DIR, ".").replace("C:\\Users\\Reynboo", "~") if title else ""
                tool_logs.append(f"🔧 <code>{html.escape(tool)}</code> {html.escape(short[:70])}")
                # keep last 3
                if len(tool_logs) > 3:
                    tool_logs = tool_logs[-3:]
                elapsed = int(time.time() - start_time)
                logs_html = "\n".join(tool_logs)
                short_model = RUNTIME_MODEL.split("/")[-1]
                html_text = f"🔧 <b>{html.escape(short_model)} tools</b> • {elapsed}s\n{logs_html}"
                if assistant_text:
                    # jika sudah ada text, gabung preview
                    preview_md = assistant_text[-1200:] if len(assistant_text) > 1200 else assistant_text
                    html_body = md_to_telegram_html(preview_md)
                    html_text += f"\n\n{html_body}"
                await throttled_edit(html_text)

            elif etype == "step_finish":
                # simpan token info jika ada
                tokens = part.get("tokens") or {}
                if tokens:
                    tokens_info = tokens
                # reset reasoning flag per step
                reasoning_active = False

            # small yield
            await asyncio.sleep(0)

        # tunggu proses selesai
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()

        # baca stderr jika error
        stderr = ""
        if proc.returncode != 0:
            try:
                err_bytes = await proc.stderr.read()
                stderr = err_bytes.decode("utf-8", errors="replace").strip()
            except:
                pass

        anim_task.cancel()
        try:
            await anim_task
        except asyncio.CancelledError:
            pass

        elapsed = int(time.time() - start_time)
        if proc.returncode != 0:
            return f"❌ Opencode exit {proc.returncode}\n{html.escape(stderr[:1000])}", tool_logs, elapsed, tokens_info

        return assistant_text, tool_logs, elapsed, tokens_info

    except Exception as e:
        anim_task.cancel()
        try:
            await anim_task
        except:
            pass
        log.exception("stream error")
        return f"❌ Error streaming: {html.escape(str(e))}", tool_logs, int(time.time()-start_time), {}


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    if not update.message or not update.message.text:
        return
    prompt = update.message.text.strip()
    if not prompt or prompt.startswith("/"):
        return

    # Kirim status awal LANGSUNG (live loading start 0s) — PnP model
    short_model = RUNTIME_MODEL.split("/")[-1]
    status_msg = await update.message.reply_text(
        f"⏳ <b>{html.escape(short_model)}</b> • mulai 0s\n<code>{html.escape(prompt[:80])}</code>\n<i>{html.escape(RUNTIME_MODEL)} • {html.escape(Path(WORK_DIR).name)}</i>",
        parse_mode=ParseMode.HTML,
    )
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    final_text, tool_logs, elapsed, tokens = await stream_opencode(prompt, status_msg, context.bot, update.effective_chat.id)

    # Format final cantik
    if final_text.startswith("❌"):
        # error, sudah html escaped sebagian
        try:
            await status_msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        except:
            await update.message.reply_text(final_text, parse_mode=ParseMode.HTML)
        return

    if not final_text or not final_text.strip():
        final_text = "(Opencode tidak mengembalikan teks, tapi tools mungkin sudah dijalankan)"
        if tool_logs:
            final_text += "\n\n" + "\n".join(tool_logs)

    # Buat header cantik — PnP model
    tok_str = ""
    if tokens:
        tok_str = f" • {tokens.get('output',0)} tok out / {tokens.get('total',0)} total"
    short_model = RUNTIME_MODEL.split("/")[-1]
    header = f"✅ <b>{html.escape(short_model)} selesai</b> • {elapsed}s{tok_str}\n<i>{html.escape(RUNTIME_MODEL)}</i>\n"
    if tool_logs:
        header += "\n".join(tool_logs) + "\n"
    header += "—" * 20

    # Gunakan split_markdown agar tiap chunk HTML valid
    chunks = split_markdown(final_text, header, 3500)

    # Edit status_msg jadi hasil akhir (split jika panjang) dengan fallback plain
    try:
        await status_msg.edit_text(chunks[0], parse_mode=ParseMode.HTML)
    except Exception as e:
        log.warning(f"final edit fail: {e}, fallback plain")
        plain = re.sub(r"<[^>]+>", "", chunks[0])
        try:
            await status_msg.edit_text(plain[:3900])
        except:
            await update.message.reply_text(chunks[0][:3900], parse_mode=ParseMode.HTML if "<" in chunks[0] else None)

    for chunk in chunks[1:]:
        try:
            await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
        except Exception as e:
            if "can't parse" in str(e).lower():
                plain = re.sub(r"<[^>]+>", "", chunk)
                await update.message.reply_text(plain[:3900])
            else:
                await update.message.reply_text(chunk[:3900])
        await asyncio.sleep(0.3)


def main():
    if "AA" not in BOT_TOKEN:
        print("ERROR: BOT_TOKEN invalid")
        return
    import shutil
    if not shutil.which("opencode"):
        print("WARNING: opencode not in PATH — PnP mode fallback ke direct LLM via env MODEL tetap jalan jika opencode tidak ada")

    print(f"PnP Live Bridge jalan. MODEL={RUNTIME_MODEL} (env MODEL={MODEL}) | WORK_DIR={WORK_DIR} | Allowed={ALLOWED_USER_IDS}")
    print(f"Metode: {'webhook '+WEBHOOK_URL if WEBHOOK_URL else 'polling (dev) — set WEBHOOK_URL untuk prod'} | Port {PORT}")
    print("Live loading: edit tiap 1.1s + spinner. Output: Telegram HTML cantik. /model set provider/model untuk ganti PnP.")
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("model", model_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("pwd", pwd_cmd))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if WEBHOOK_URL:
        # PnP webhook prod — git clone anywhere (Railway/Render/Fly/VPS)
        print(f"Starting webhook: {WEBHOOK_URL} secret={'set' if WEBHOOK_SECRET else 'none'}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="webhook",
            webhook_url=WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET if WEBHOOK_SECRET else None,
            drop_pending_updates=True,
        )
    else:
        app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
