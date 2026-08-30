"""
Telegram -> Opencode Bridge (polling, untuk belajar lokal)
Cara kerja: chat Telegram => jalankan `opencode run "pesan kamu"` di WORK_DIR => balas hasilnya ke Telegram

Keamanan: hanya chat_id kamu (1925430810) yang boleh pakai bot.
"""
import asyncio
import html
import logging
import os
import re
import textwrap
from pathlib import Path

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# === KONFIGURASI ===
# GANTI dengan token baru kamu setelah revoke. Lebih aman pakai env var: set TELEGRAM_BOT_TOKEN=xxx
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8808398800:AAGG9aG3iupOpurz-lqJ7LghZC0-M2f9tsQ")
# Hanya user ini yang boleh trigger opencode (isi dari getUpdates kamu)
ALLOWED_USER_IDS = {1925430810}  # ReynaldiRafi
# Folder project yang akan dikerjakan opencode. Ganti ke project kamu, contoh: r"D:\kuliah\skripsi"
# Kalau dikosongkan/opencode tidak butuh dir spesifik, pakai folder bridge ini sendiri
WORK_DIR = str(Path(__file__).parent.resolve())
# Model opencode (kosongkan = pakai dari opencode.jsonc)
OPENCODE_MODEL = ""  # contoh: "opencode/muse-spark-1.2-contributor-free"
# Timeout opencode run (ms ada di opencode.jsonc, tapi subprocess kita batasi 5 menit)
TIMEOUT_SECONDS = 300

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# === FORMATTER KHUSUS TELEGRAM (HTML) ===
# Telegram HTML yang didukung: <b> <i> <u> <s> <code> <pre> <blockquote> <a href="">
# Markdown dari opencode dikonversi ke HTML agar tidak muncul raw ** di Telegram.

_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_CODEBLOCK_RE = re.compile(r"```(\w+)?\n?(.*?)```", re.DOTALL)
_INLINE_RE = re.compile(r"`([^`\n]+)`")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _escape_html(text: str) -> str:
    return html.escape(text, quote=False)


def markdown_to_telegram_html(raw: str) -> str:
    """Konversi output opencode (markdown-ish) ke HTML Telegram yang rapi.

    - strip ANSI
    - ```code``` -> <pre> / <pre><code class="language-...">
    - `inline` -> <code>
    - **bold** / __bold__ -> <b>
    - *italic* / _italic_ -> <i>
    - ~~strike~~ -> <s>
    - [text](url) -> <a href="">
    - # Header -> <b>Header</b>
    - > quote -> <blockquote>
    - - bullet -> • bullet
    - collapse blank lines
    """
    if not raw:
        return ""

    text = strip_ansi(raw).replace("\r\n", "\n")

    # 1) Amankan code block dulu dengan placeholder
    code_blocks: dict[str, str] = {}

    def _repl_block(m: re.Match) -> str:
        lang = (m.group(1) or "").strip()
        code = m.group(2) or ""
        # hilangkan newline trailing yang sering bikin <pre> kosong di akhir
        code = code.strip("\n")
        code_esc = _escape_html(code)
        if lang:
            html_block = f'<pre><code class="language-{_escape_html(lang)}">{code_esc}</code></pre>'
        else:
            html_block = f"<pre>{code_esc}</pre>"
        key = f"__CB_{len(code_blocks)}__"
        code_blocks[key] = html_block
        return key

    text = _CODEBLOCK_RE.sub(_repl_block, text)

    # 2) Amankan inline code
    inline_codes: dict[str, str] = {}

    def _repl_inline(m: re.Match) -> str:
        code = _escape_html(m.group(1))
        key = f"__IC_{len(inline_codes)}__"
        inline_codes[key] = f"<code>{code}</code>"
        return key

    text = _INLINE_RE.sub(_repl_inline, text)

    # 3) Escape HTML untuk sisa teks (placeholder aman karena alphanumeric)
    text = _escape_html(text)

    # 4) Link [text](https://...)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^\)\s]+)\)", r'<a href="\2">\1</a>', text)

    # 5) Bold **text** dan __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text, flags=re.DOTALL)

    # 6) Strikethrough ~~text~~
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text, flags=re.DOTALL)

    # 7) Italic *text* dan _text_ (hindari tabrakan dengan bold yang sudah jadi <b>)
    # hanya match single delimiter yang tidak dobel
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text, flags=re.DOTALL)
    text = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", text, flags=re.DOTALL)

    # 8) Header, blockquote, bullet per baris
    lines = text.split("\n")
    out_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        # header: #..## Header
        m = re.match(r"^#{1,6}\s+(.*)", stripped)
        if m:
            out_lines.append(f"<b>{m.group(1).strip()}</b>")
            continue
        # blockquote
        m = re.match(r"^&gt;\s?(.*)", line.strip())  # &gt; karena sudah di-escape
        if m:
            # m.group(1) sudah escaped, tapi di dalamnya mungkin ada <b>/<i> tag -> jangan double escape
            # karena tag sudah jadi <b> setelah step di atas, tapi &gt; escape membuat deteksi tricky
            # kita pakai raw check sebelum escape? lebih aman cek original line sebelum escape sudah hilang.
            # Fallback: jika line mulai dengan &gt; anggap quote
            out_lines.append(f"<blockquote>{m.group(1)}</blockquote>")
            continue
        # bullet - / *  (hati-hati * sudah jadi <i> sebagian, tapi bullet di awal baris masih "- " atau "* ")
        m = re.match(r"^\s*[-•]\s+(.*)", line)
        if m:
            out_lines.append(f"• {m.group(1)}")
            continue
        # handle raw "* " yang belum ke-convert karena di-escaped? "*" tidak di-escape, jadi masih "*"
        m2 = re.match(r"^\s*\*\s+(.*)", line)
        if m2:
            out_lines.append(f"• {m2.group(1)}")
            continue
        out_lines.append(line)

    text = "\n".join(out_lines)

    # 9) Horizontal rule
    text = re.sub(r"\n-{3,}\n", "\n──────────\n", text)
    text = re.sub(r"\n_{3,}\n", "\n──────────\n", text)

    # 10) Kembalikan placeholder inline & block
    for k, v in inline_codes.items():
        text = text.replace(k, v)
    for k, v in code_blocks.items():
        text = text.replace(k, v)

    # 11) Rapikan blank lines & spasi trailing
    text = re.sub(r" +\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def smart_split_html(text: str, limit: int = 4000) -> list[str]:
    """Split HTML Telegram dengan aman:
    - prioritas split di boundary \n\n atau \n
    - tidak memotong di tengah <pre>...</pre> jika masih muat
    - jika satu <pre> block > limit, pecah paksa di dalam code dengan buka-tutup tag
    """
    if len(text) <= limit:
        return [text]

    # Jika ada <pre> sangat panjang, pecah dulu block tersebut secara khusus
    # Strategi: split per baris, akumulasi
    lines = text.split("\n")
    chunks: list[str] = []
    cur = ""

    # state: apakah kita sedang di dalam <pre> yang belum ditutup di chunk saat ini
    # Untuk sederhana: cek apakah cur mengandung <pre> tanpa </pre> penutup
    def _is_inside_pre(s: str) -> bool:
        return s.count("<pre>") > s.count("</pre>") or s.count('<pre><code') > s.count("</code></pre>")

    for line in lines:
        # jika satu baris sendiri > limit (biasanya <pre> panjang tanpa newline) -> force cut
        if len(line) > limit:
            # flush cur dulu
            if cur:
                chunks.append(cur)
                cur = ""
            # force cut line
            for i in range(0, len(line), limit):
                part = line[i : i + limit]
                # jika ini bagian dari pre, bungkus agar tetap monospace di Telegram
                # tapi jangan dobel <pre> kalau sudah ada
                if "<pre>" in part or "</pre>" in part:
                    chunks.append(part)
                else:
                    # cek apakah kita sedang inside pre dari chunk sebelumnya? fallback: kirim sebagai <pre> lanjutan
                    chunks.append(part)
            continue

        candidate = (cur + "\n" + line) if cur else line
        # +1 untuk newline
        if len(candidate) > limit:
            # coba cari split point yang lebih natural: jika cur sudah ada, flush
            # pastikan tidak memotong di tengah <pre> terbuka
            if _is_inside_pre(cur):
                # tutup pre di chunk ini, buka lagi di next
                # cari closing tag terdekat? sederhana: tutup dan buka
                # deteksi jenis pre
                has_lang = '<pre><code class=' in cur
                # tutup
                if has_lang:
                    # pastikan ditutup dengan </code></pre> jika belum
                    if not cur.rstrip().endswith("</code></pre>"):
                        cur += "</code></pre>"
                else:
                    if not cur.rstrip().endswith("</pre>"):
                        cur += "</pre>"
                chunks.append(cur)
                # buka baru untuk lanjutannya (ambil lang jika ada)
                if has_lang:
                    # extract lang class dari cur
                    m = re.search(r'<code class="language-([^"]+)">', cur)
                    lang = m.group(1) if m else ""
                    cur = f'<pre><code class="language-{lang}">' + line if lang else "<pre>" + line
                else:
                    cur = "<pre>" + line
            else:
                chunks.append(cur)
                cur = line
        else:
            cur = candidate

    if cur:
        # balance pre tag jika masih terbuka di chunk terakhir
        if _is_inside_pre(cur):
            if '<pre><code class=' in cur:
                if not cur.rstrip().endswith("</code></pre>"):
                    cur += "</code></pre>"
            else:
                if not cur.rstrip().endswith("</pre>"):
                    cur += "</pre>"
        chunks.append(cur)

    # final safety: pastikan tidak ada chunk > limit (jika masih, force cut)
    final: list[str] = []
    for c in chunks:
        if len(c) <= limit:
            final.append(c)
        else:
            for i in range(0, len(c), limit):
                final.append(c[i : i + limit])
    return final


def build_telegram_chunks(raw_output: str, prompt: str, limit: int = 4000) -> list[str]:
    """Hasilkan chunk siap kirim ke Telegram (HTML). Chunk pertama ada header prompt."""
    body = markdown_to_telegram_html(raw_output)
    if not body:
        body = "<i>(opencode tidak mengembalikan output)</i>"

    # Header ringkas untuk konteks
    prompt_esc = _escape_html(prompt[:300])
    header = f"<b>✅ Opencode selesai</b>\n<blockquote>{prompt_esc}</blockquote>\n\n"

    # Jika body pendek, gabung header+body dalam 1 chunk jika muat
    if len(header) + len(body) <= limit:
        return [header + body]

    # Body di-split dulu, lalu header ditempel ke chunk pertama
    body_chunks = smart_split_html(body, limit=limit - 500)  # beri ruang header/footer
    result: list[str] = []
    total = len(body_chunks)
    for i, bc in enumerate(body_chunks):
        page_info = f"\n\n<i>— {i+1}/{total}</i>" if total > 1 else ""
        if i == 0:
            # header hanya di chunk 1; kalau header + bc + footer > limit, pangkas header
            chunk = header + bc + page_info
            if len(chunk) > limit:
                # fallback: header terpisah
                result.append(header.rstrip())
                result.append(bc + page_info)
            else:
                result.append(chunk)
        else:
            result.append(bc + page_info)
    return result

def is_allowed(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else None
    return uid in ALLOWED_USER_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    await update.message.reply_text(
        textwrap.dedent(f"""
        <b>Halo Reynaldi! Bot jembatan Telegram ↔ Opencode aktif ✅</b>

        <b>WORK_DIR:</b> <code>{_escape_html(WORK_DIR)}</code>

        Kirim pesan apapun, nanti aku teruskan ke <code>opencode run</code> dan balasin hasilnya di sini.

        <b>Perintah:</b>
        /start - pesan ini
        /id - lihat chat_id kamu
        /pwd - lihat WORK_DIR
        /help - bantuan

        <i>Output opencode diformat khusus Telegram (HTML) agar rapi, code block tetap monospace.</i>
        """),
        parse_mode="HTML",
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Cara pakai</b>\n"
        "Kirim pesan natural language, contoh:\n"
        "• <code>buatkan function hitung NDVI di src/ndvi.py</code>\n"
        "• <code>fix bug di bot_bridge.py line 50</code>\n"
        "• <code>jelaskan isi folder ini</code>\n\n"
        "Bot akan jalankan <code>opencode run \"pesan kamu\" --dir WORK_DIR</code> dan kirim outputnya balik.\n"
        "<i>Tip: output panjang otomatis dipecah 1/2/3... tanpa memotong code block.</i>",
        parse_mode="HTML",
    )

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"chat_id kamu: <code>{update.effective_chat.id}</code>\nuser_id: <code>{update.effective_user.id}</code>",
        parse_mode="HTML",
    )

async def pwd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"<b>WORK_DIR:</b> <code>{_escape_html(WORK_DIR)}</code>", parse_mode="HTML")

async def run_opencode(prompt: str) -> str:
    """Jalankan `opencode run` sebagai subprocess dan kembalikan output."""
    cmd = ["opencode", "run", prompt, "--dir", WORK_DIR, "--format", "default"]
    if OPENCODE_MODEL:
        cmd.extend(["--model", OPENCODE_MODEL])
    # --auto agar tidak minta approval permission di bridge (hati-hati, untuk belajar saja)
    # Hapus "--auto" kalau mau tetap konfirmasi manual di log
    cmd.append("--auto")

    log.info(f"Running: {' '.join(cmd)}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            proc.kill()
            return f"⏰ Timeout {TIMEOUT_SECONDS}s. Opencode masih jalan di background, cek terminal."

        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            return f"❌ opencode exit {proc.returncode}\n\n{err or out or '(no output)'}"

        # batasi biar tidak kepanjangan
        combined = out if out else err
        if not combined:
            return "(opencode tidak mengembalikan output)"
        return combined
    except FileNotFoundError:
        return "❌ `opencode` tidak ditemukan di PATH. Pastikan `opencode --version` jalan di PowerShell."
    except Exception as e:
        log.exception("run_opencode failed")
        return f"❌ Error bridge: {e}"

def split_telegram(text: str, limit: int = 4000):
    """Fallback plain split jika HTML parsing gagal."""
    for i in range(0, len(text), limit):
        yield text[i:i+limit]

async def _send_chunks_html(update: Update, chunks: list[str]):
    """Kirim chunks dengan parse_mode HTML, fallback ke plain text jika BadRequest."""
    for chunk in chunks:
        try:
            await update.message.reply_text(chunk, parse_mode="HTML", disable_web_page_preview=True)
        except BadRequest as e:
            log.warning(f"HTML parse gagal ({e}), fallback plain: {e}")
            # Fallback: escape semua tag, kirim plain
            plain = re.sub(r"<[^>]+>", "", chunk)
            # batasi lagi
            for p in split_telegram(plain, 4000):
                try:
                    await update.message.reply_text(p, disable_web_page_preview=True)
                except Exception:
                    await update.message.reply_text(p[:4000])
        except Exception as e:
            log.exception("send chunk failed")
            # last resort plain
            plain = re.sub(r"<[^>]+>", "", chunk)
            await update.message.reply_text(plain[:4000], disable_web_page_preview=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    if not update.message or not update.message.text:
        return

    prompt = update.message.text.strip()
    if not prompt:
        return

    # Abaikan command yang sudah di-handle
    if prompt.startswith("/"):
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    prompt_preview = _escape_html(prompt[:200])
    status_msg = await update.message.reply_text(
        f"⏳ <b>Meneruskan ke opencode...</b>\n<blockquote>{prompt_preview}</blockquote>",
        parse_mode="HTML",
    )

    result = await run_opencode(prompt)

    # Edit status lalu kirim hasil (format khusus Telegram)
    try:
        await status_msg.edit_text("✅ <b>Opencode selesai</b>, mengirim hasil...", parse_mode="HTML")
    except Exception:
        pass

    chunks = build_telegram_chunks(result, prompt, limit=4000)

    # Jika output super panjang (>5 chunk), kirim ringkas + file .txt sebagai opsi
    if len(chunks) > 5:
        summary = chunks[:5]
        summary[-1] += f"\n\n<i>... dipotong {len(chunks)-5} bagian lagi (total {len(chunks)}). Mengirim file lengkap...</i>"
        await _send_chunks_html(update, summary)
        # kirim file lengkap sebagai document
        try:
            full_plain = strip_ansi(result)
            # batasi file 1MB
            file_path = Path(WORK_DIR) / "_opencode_output.txt"
            # tulis ke temp agar tidak polusi WORK_DIR jika bukan di situ -> pakai TEMP
            import tempfile
            tmp = Path(tempfile.gettempdir()) / f"opencode_{update.effective_user.id}.txt"
            tmp.write_text(full_plain[:500_000], encoding="utf-8")
            await update.message.reply_document(
                document=open(tmp, "rb"),
                filename="opencode_output.txt",
                caption=f"<b>Output lengkap</b> ({len(full_plain)} chars, {len(chunks)} halaman)",
                parse_mode="HTML",
            )
        except Exception as e:
            log.warning(f"Gagal kirim file lengkap: {e}")
            # fallback kirim sisa chunks
            await _send_chunks_html(update, chunks[5:])
    else:
        await _send_chunks_html(update, chunks)

    log.info(f"Done for prompt: {prompt[:80]} | chunks={len(chunks)}")


def main():
    if "AA" not in BOT_TOKEN or BOT_TOKEN.startswith("GANTI"):
        print("ERROR: BOT_TOKEN belum diisi. Set env TELEGRAM_BOT_TOKEN atau edit BOT_TOKEN di file ini.")
        return

    # Cek opencode ada
    import shutil
    if not shutil.which("opencode"):
        print("WARNING: `opencode` tidak di PATH. Pastikan sudah install via scoop.")

    # Cek WORK_DIR ada
    if not Path(WORK_DIR).exists():
        print(f"WARNING: WORK_DIR tidak ada: {WORK_DIR}")

    print(f"Bridge jalan. WORK_DIR={WORK_DIR} | Allowed={ALLOWED_USER_IDS}")
    print("Tekan Ctrl+C untuk stop. Laptop harus nyala agar bot balas.")

    # Fix Python 3.14: pastikan event loop ada sebelum run_polling
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("pwd", pwd_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
