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
import sys
import time
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# === LOAD .env manual (tanpa butuh python-dotenv) ===
try:
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        for _line in _env_path.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            _k = _k.strip()
            _v = _v.strip().strip('"').strip("'")
            if _k and _k not in os.environ:
                os.environ[_k] = _v
except Exception:
    pass

# === KONFIG PnP — semua dari env biar git clone anywhere ===
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_USER_IDS = {int(x.strip()) for x in os.getenv("ALLOWED_USER_IDS", "1925430810").split(",") if x.strip().isdigit()}
WORK_DIR = os.getenv("WORK_DIR", str(Path(__file__).parent.resolve()))  # GANTI via .env: r"D:\Riset\HyperSpectral"
# PnP model: set via .env MODEL atau /model di Telegram — default muse-spark gratis
MODEL = os.getenv("MODEL", os.getenv("OPENCODE_MODEL", "opencode/muse-spark-1.2-contributor-free"))
# PnP metode: kosong = polling (dev), isi = webhook prod (https://your-app.up.railway.app/webhook)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
PORT = int(os.getenv("PORT", "8000"))
TIMEOUT_SECONDS = int(os.getenv("TIMEOUT_SECONDS", "300"))
ENABLE_AUTO_RESTART = os.getenv("ENABLE_AUTO_RESTART", "1").strip() != "0"
# Feature flags — matikan instant tanpa edit code jika fitur bikin bug
FEATURE_WORKDIR = os.getenv("FEATURE_WORKDIR", "1").strip() != "0"
FEATURE_SESSIONS = os.getenv("FEATURE_SESSIONS", "1").strip() != "0"
FEATURE_CLEANUP = os.getenv("FEATURE_CLEANUP", "1").strip() != "0"
FEATURE_VOICE = os.getenv("FEATURE_VOICE", "1").strip() != "0"
FEATURE_DOC = os.getenv("FEATURE_DOC", "1").strip() != "0"
FEATURE_QUEUE = os.getenv("FEATURE_QUEUE", "1").strip() != "0"
# Runtime model override per-process (via /model set)
RUNTIME_MODEL = MODEL
FALLBACK_MODEL = __import__("os").getenv("FALLBACK_MODEL", "groq/llama-3.3-70b-versatile")

# === SESSION CONTINUITY (persist active session per chat+WORK_DIR) ===
_STATE_FILE = Path(__file__).parent / ".bridge_state.json"
#   new: {"active": {"1925430810|C:\\work": "ses_xxx"}, "work_dir": "..."}
#   legacy migration: flat {"1925430810": "ses_xxx"} -> auto-migrated to workdir-scoped key
RUNTIME_WORK_DIR = WORK_DIR  # mutable via /workdir

def _active_key(chat_id: int) -> str:
    try:
        # cross-platform: Windows lowers, Linux keeps case; resolve handles /app vs C:\\ vs symlink
        norm = str(Path(RUNTIME_WORK_DIR).resolve()).lower() if __import__("os").name=="nt" else str(Path(RUNTIME_WORK_DIR).resolve())
    except Exception:
        norm = str(RUNTIME_WORK_DIR).lower() if __import__("os").name=="nt" else str(RUNTIME_WORK_DIR)
    return f"{chat_id}|{norm}"

def _load_state() -> dict:
    try:
        if _STATE_FILE.exists():
            raw = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            # migrate legacy flat keys (no |) -> workdir-scoped
            active = raw.get("active", {}) or {}
            needs_migrate = any("|" not in k for k in list(active.keys()))
            if needs_migrate:
                migrated: dict = {}
                for k, v in list(active.items()):
                    if "|" in k:
                        migrated[k] = v
                    else:
                        # old chat_id only -> map to current RUNTIME_WORK_DIR
                        try:
                            cid = int(k)
                            migrated[_active_key(cid)] = v
                        except Exception:
                            migrated[k] = v
                raw["active"] = migrated
                # persist migration quietly
                try:
                    _STATE_FILE.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
                except Exception:
                    pass
            return raw
    except Exception as e:
        # log not yet defined at import time; use print fallback
        try:
            log.debug(f"load_state fail: {e}")
        except Exception:
            pass
    return {"active": {}}

def _save_state(s: dict):
    try:
        _STATE_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        try:
            log.warning(f"save_state fail: {e}")
        except Exception:
            pass

def get_active_session(chat_id: int) -> str | None:
    st = _load_state()
    return st.get("active", {}).get(_active_key(chat_id))

def set_active_session(chat_id: int, session_id: str | None):
    st = _load_state()
    active = st.get("active", {}) or {}
    k = _active_key(chat_id)
    if session_id:
        active[k] = session_id
    else:
        active.pop(k, None)
    st["active"] = active
    _save_state(st)

def clear_active_session(chat_id: int):
    set_active_session(chat_id, None)

def get_all_active_for_chat(chat_id: int) -> dict:
    """Return {workdir_norm: session_id} for this chat."""
    st = _load_state()
    prefix = f"{chat_id}|"
    out = {}
    for k, v in (st.get("active") or {}).items():
        if k.startswith(prefix):
            out[k[len(prefix):]] = v
    return out

# === ANTI-SPAM & QUEUE ===
_LAST_MSG_TIME: dict[int,float] = {}
_ACTIVE_JOBS: dict[int, asyncio.Task] = {}
_JOB_PROCS: dict[int, asyncio.subprocess.Process] = {}
_RATE_LIMIT_SEC = 2.5
_QUEUE: dict[int, str] = {}

# Auto-restart setelah edit bridge — PnP self-healing (watch file mtime + flag)
_SELF_PATH = Path(__file__).resolve()
_SELF_MTIME = _SELF_PATH.stat().st_mtime if _SELF_PATH.exists() else 0
_RESTART_FLAG = Path(__file__).parent / ".restart"
_RESTART_FLAG2 = Path(__file__).parent / ".bridge_restart"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)
# mask BOT_TOKEN in logs (security)
class _TokenMaskFilter(logging.Filter):
    def filter(self, record):
        try:
            msg = record.getMessage()
            if BOT_TOKEN and BOT_TOKEN in msg:
                record.msg = record.msg.replace(BOT_TOKEN, "***BOT_TOKEN***")
                if record.args:
                    # also mask args tuple
                    record.args = tuple(str(a).replace(BOT_TOKEN, "***BOT_TOKEN***") if isinstance(a,str) else a for a in record.args)
        except Exception:
            pass
        return True
try:
    logging.getLogger().addFilter(_TokenMaskFilter())
    log.addFilter(_TokenMaskFilter())
except Exception:
    pass

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


# ===== SESSION LISTING HELPERS (filter by RUNTIME_WORK_DIR) =====
async def fetch_sessions(limit: int = 30, query: str | None = None) -> list[dict]:
    """Ambil daftar session opencode, filter by RUNTIME_WORK_DIR, sort updated desc, optional query filter."""
    cmd = ["opencode", "session", "list", "--format", "json"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        raw = stdout.decode("utf-8", errors="replace").strip()
        if not raw:
            return []
        data = json.loads(raw)
        norm_work = str(Path(RUNTIME_WORK_DIR).resolve()).lower() if RUNTIME_WORK_DIR else ""
        filtered = []
        for s in data:
            d = str(s.get("directory", "")).lower()
            if d == norm_work or norm_work in d or d in norm_work:
                filtered.append(s)
        pool = filtered if filtered else data
        # query filter
        if query:
            q = query.lower().strip()
            pool = [s for s in pool if q in str(s.get("title","")).lower() or q in str(s.get("id","")).lower()]
        pool.sort(key=lambda x: x.get("updated", 0), reverse=True)
        return pool[:limit] if limit else pool
    except Exception as e:
        log.warning(f"fetch_sessions fail: {e}")
        return []

async def fetch_all_sessions_raw(limit: int = 100) -> list[dict]:
    """Raw without WORK_DIR filter (untuk /workdir list)."""
    return await fetch_sessions(limit=limit, query=None)

def fmt_time(ms: int) -> str:
    try:
        # ms epoch -> local
        import datetime
        dt = datetime.datetime.fromtimestamp(ms / 1000)
        return dt.strftime("%d/%m %H:%M")
    except:
        return str(ms)

def build_sessions_html(sessions: list[dict], active_id: str | None, limit: int = 10, page: int = 0, page_size: int = 10) -> str:
    if not sessions:
        return "<i>Belum ada session di direktori ini. Kirim pesan untuk buat baru.</i>"
    start = page * page_size
    slice_s = sessions[start:start+page_size]
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
    total_pages = (len(sessions) + page_size -1)//page_size
    footer = f"\n\n<i>Halaman {page+1}/{max(1,total_pages)} • total {len(sessions)} session di WORK_DIR</i>" if total_pages>1 else ""
    return "\n\n".join(lines) + footer

def build_sessions_keyboard(sessions: list[dict], active_id: str | None, limit: int = 10, cols: int = 5, page: int = 0, page_size: int = 10, query: str | None = None):
    """Inline keyboard: nomor 1..N per halaman + pagination + aksi."""
    kb = []
    start = page * page_size
    slice_s = sessions[start:start+page_size]
    row = []
    for idx, s in enumerate(slice_s, start + 1):
        sid = s.get("id", "")
        label = f"{'✅' if sid==active_id else ''}{idx}"
        row.append(InlineKeyboardButton(label.strip() or str(idx), callback_data=f"sw:{sid}"))
        if len(row) >= cols:
            kb.append(row); row = []
    if row:
        kb.append(row)
    # pagination row if needed
    total_pages = (len(sessions) + page_size -1)//page_size
    if total_pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"sw:page:{page-1}"))
        if page < total_pages -1:
            nav.append(InlineKeyboardButton("Next ▶", callback_data=f"sw:page:{page+1}"))
        if nav:
            kb.append(nav)
    # aksi
    kb.append([
        InlineKeyboardButton("🆕 New", callback_data="sw:new"),
        InlineKeyboardButton("🔄 Refresh", callback_data="sw:refresh"),
        InlineKeyboardButton("📁 Workdir", callback_data="sw:workdir"),
    ])
    return InlineKeyboardMarkup(kb)


def is_allowed(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else None
    return uid in ALLOWED_USER_IDS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    mode = "webhook" if WEBHOOK_URL else "polling"
    active = get_active_session(update.effective_chat.id) if update.effective_chat else None
    active_str = f"<code>{html.escape(active)}</code> ✅" if active else "<i>(belum ada — pesan baru akan buat session)</i>"
    await update.message.reply_text(
        f"✨ <b>Live Bridge PnP Aktif</b> • <code>{html.escape(RUNTIME_MODEL)}</code>\n\n"
        f"WORK_DIR: <code>{html.escape(RUNTIME_WORK_DIR)}</code>\n"
        f"Session aktif: {active_str}\n"
        f"Mode: <code>{mode}</code> {'('+html.escape(WEBHOOK_URL)+')' if WEBHOOK_URL else '(dev, laptop harus nyala)'}\n"
        f"Model PnP: <code>{html.escape(RUNTIME_MODEL)}</code>\n\n"
        f"Kirim prompt natural, aku streaming langsung — bukan nunggu buta.\n"
        f"Contoh: <i>buatkan file hello.py print halo dunia</i>\n\n"
        f"<b>Perintah:</b>\n"
        f"/sessions [n] [kata] - list session di WORK_DIR (tap nomor untuk switch)\n"
        f"/switch [n|ses_xxx] - ganti session\n"
        f"/workdir [path|list] - ganti project dir (per-chat per-dir mapping)\n"
        f"/new - session baru (reset konteks)\n"
        f"/status - status + queue\n"
        f"/rename <judul> - rename session aktif\n"
        f"/delete [ses_xxx] - hapus session\n"
        f"/fork [pesan] - fork session aktif\n"
        f"/share - share session aktif\n"
        f"/export - export session ke .md\n"
        f"/model - lihat & ganti model\n"
        f"/health - health + uptime\n"
        f"/logs [n] - tail bridge log\n"
        f"/allow [add|remove <id>] - kelola akses\n"
        f"/cancel - batalkan job aktif\n"
        f"/pwd /id /restart /help",
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
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    await update.message.reply_text(
        f"chat_id: <code>{update.effective_chat.id}</code>\nuser_id: <code>{update.effective_user.id}</code>",
        parse_mode=ParseMode.HTML,
    )


async def pwd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    active = get_active_session(update.effective_chat.id) if update.effective_chat else None
    active_str = f"\nSession aktif: <code>{html.escape(active)}</code>" if active else "\nSession aktif: <i>(fresh)</i>"
    await update.message.reply_text(f"WORK_DIR: <code>{html.escape(RUNTIME_WORK_DIR)}</code>{active_str}\n<i>Env WORK_DIR: <code>{html.escape(WORK_DIR)}</code></i>", parse_mode=ParseMode.HTML)

# === /workdir — list & switch project directory at runtime ===
async def workdir_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global RUNTIME_WORK_DIR
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    args = context.args or []
    if not args:
        active = get_active_session(update.effective_chat.id) if update.effective_chat else None
        # list candidates from common parents
        candidates = []
        try:
            cur = Path(RUNTIME_WORK_DIR).resolve()
            parent = cur.parent
            if parent.exists():
                for p in parent.iterdir():
                    if p.is_dir() and not p.name.startswith("."):
                        candidates.append(str(p))
                        if len(candidates) >= 12:
                            break
        except Exception:
            pass
        # add fixed bridge dir
        bridge_dir = str(Path(__file__).parent.resolve())
        if bridge_dir not in candidates:
            candidates.insert(0, bridge_dir)
        cand_html = "\n".join(f"• <code>{html.escape(c)}</code>" for c in candidates[:12])
        await update.message.reply_text(
            f"📁 <b>WORK_DIR aktif</b>: <code>{html.escape(RUNTIME_WORK_DIR)}</code>\n"
            f"Session aktif: <code>{html.escape(active) if active else '-'}</code>\n\n"
            f"<b>Kandidat di parent:</b>\n{cand_html}\n\n"
            f"Ganti: <code>/workdir C:\\path\\ke\\project</code> atau <code>/workdir list</code>\n"
            f"<i>Setelah ganti, /sessions akan tampilkan session di direktori itu. Mapping session per-WORK_DIR terpisah, konteks lama tidak hilang.</i>",
            parse_mode=ParseMode.HTML,
        )
        return
    if args[0] == "list":
        # same as no args but also show all sessions per workdir
        sessions = await fetch_sessions(limit=100)
        by_dir: dict[str,int] = {}
        for s in sessions:
            d = s.get("directory","?")
            by_dir[d] = by_dir.get(d,0)+1
        lines = "\n".join(f"• <code>{html.escape(k)}</code> — {v} sesi" for k,v in list(by_dir.items())[:12])
        await update.message.reply_text(f"📊 <b>WORK_DIR aktif</b>: <code>{html.escape(RUNTIME_WORK_DIR)}</code>\n\n<b>Session count per direktori (sample):</b>\n{lines or '<i>kosong</i>'}", parse_mode=ParseMode.HTML)
        return
    # set new workdir
    new_path = " ".join(args).strip().strip('"').strip("'")
    p = Path(new_path)
    # allow relative
    if not p.is_absolute():
        p = (Path(RUNTIME_WORK_DIR) / p).resolve()
    if not p.exists():
        await update.message.reply_text(f"❌ Path tidak ada: <code>{html.escape(str(p))}</code>", parse_mode=ParseMode.HTML)
        return
    if not p.is_dir():
        await update.message.reply_text(f"❌ Bukan direktori: <code>{html.escape(str(p))}</code>", parse_mode=ParseMode.HTML)
        return
    RUNTIME_WORK_DIR = str(p.resolve())
    active = get_active_session(update.effective_chat.id)
    await update.message.reply_text(
        f"✅ <b>WORK_DIR diganti</b> → <code>{html.escape(RUNTIME_WORK_DIR)}</code>\n"
        f"Session aktif di dir ini: <code>{html.escape(active) if active else '-'}</code>\n\n"
        f"<i>Kirim pesan untuk lanjut/buat session di direktori baru. /sessions untuk lihat.</i>",
        parse_mode=ParseMode.HTML,
    )
    log.info(f"WORK_DIR switched to {RUNTIME_WORK_DIR} by {update.effective_user.id}")


async def restart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    await update.message.reply_text("♻️ Restarting bridge... (auto-restart loop akan nyalakan lagi 5s)", parse_mode=ParseMode.HTML)
    log.info(f"Manual restart by {update.effective_user.id}")
    # Beri waktu kirim pesan dulu
    await asyncio.sleep(1)
    # Trigger loop restart via exit 0 (run_bridge_loop akan restart)
    os._exit(0)


async def sessions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    args = context.args or []
    n = 10
    query: str | None = None
    page = 0
    # parse: /sessions [n] [query]  or /sessions search <query>
    if args:
        if args[0].isdigit():
            try: n = max(1, min(20, int(args[0])))
            except: n = 10
            if len(args) > 1:
                # check page= N
                rest = args[1:]
                # support "page 2"
                if len(rest) >= 2 and rest[0] == "page" and rest[1].isdigit():
                    page = max(0, int(rest[1])-1)
                    query = " ".join(rest[2:]) if len(rest) > 2 else None
                else:
                    query = " ".join(rest)
                    if not query.strip():
                        query = None
        elif args[0] == "page" and len(args) >= 2 and args[1].isdigit():
            page = max(0, int(args[1])-1)
            query = " ".join(args[2:]) if len(args) > 2 else None
        else:
            query = " ".join(args)
            if not query.strip():
                query = None
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    sessions = await fetch_sessions(limit=100, query=query)
    active = get_active_session(update.effective_chat.id)
    page_size = n
    html_body = build_sessions_html(sessions, active, limit=page_size, page=page, page_size=page_size)
    kb = build_sessions_keyboard(sessions, active, limit=page_size, page=page, page_size=page_size, query=query)
    qinfo = f" • filter: <i>{html.escape(query)}</i>" if query else ""
    header = f"📂 <b>Sessions di WORK_DIR</b> • <code>{html.escape(RUNTIME_WORK_DIR)}</code>{qinfo}\nAktif: <code>{html.escape(active) if active else '-'}</code> • Hal {page+1}\nTap nomor untuk <b>/switch</b> instant — konteks tidak hilang.\n— — —\n"
    text = header + html_body + f"\n\n<i>Tip: /switch 2 atau /switch ses_xxx atau tap tombol. /sessions 20 cari-kata untuk filter. /workdir untuk ganti project.</i>"
    if len(text) > 3800:
        for part in split_html(text, 3800):
            await update.message.reply_text(part, parse_mode=ParseMode.HTML)
        await update.message.reply_text("Pilih session:", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def switch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    args = context.args or []
    if not args:
        return await sessions_cmd(update, context)
    target = args[0].strip()
    sessions = await fetch_sessions(limit=100)
    chosen = None
    if target.isdigit():
        idx = int(target)
        if 1 <= idx <= len(sessions):
            chosen = sessions[idx-1].get("id")
        else:
            await update.message.reply_text(f"❌ Nomor {idx} di luar jangkauan (1..{len(sessions)})", parse_mode=ParseMode.HTML)
            return
    elif target.startswith("ses_"):
        chosen = target
        if not any(s.get("id")==chosen for s in sessions):
            await update.message.reply_text(f"⚠️ Session <code>{html.escape(chosen)}</code> tidak ada di list WORK_DIR saat ini, tapi tetap di-switch (mungkin beda WORK_DIR).", parse_mode=ParseMode.HTML)
    else:
        # maybe query?
        await update.message.reply_text("Gunakan: <code>/switch 2</code> atau <code>/switch ses_xxx</code> atau <code>/switch</code> untuk list", parse_mode=ParseMode.HTML)
        return
    if chosen:
        set_active_session(update.effective_chat.id, chosen)
        title = next((s.get("title","") for s in sessions if s.get("id")==chosen), "")
        await update.message.reply_text(
            f"✅ <b>Switched</b> → <code>{html.escape(chosen)}</code>\n<i>{html.escape(title)}</i>\n\nKirim pesan selanjutnya akan <b>lanjut konteks session ini</b> (<code>--session {html.escape(chosen)}</code>).",
            parse_mode=ParseMode.HTML,
        )
        log.info(f"Switch {update.effective_user.id} -> {chosen}")

async def new_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    clear_active_session(update.effective_chat.id)
    await update.message.reply_text(
        "🆕 <b>Session di-reset</b>\nPesan selanjutnya akan buat session baru (fresh konteks).\n\n<i>Session lama tetap ada di laptop — bisa /switch lagi kapan saja.</i>",
        parse_mode=ParseMode.HTML,
    )
    log.info(f"New session (clear) by {update.effective_user.id}")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    active = get_active_session(update.effective_chat.id)
    sessions = await fetch_sessions(limit=100)
    title = ""
    dir_of = ""
    if active:
        for s in sessions:
            if s.get("id")==active:
                title = s.get("title","")
                dir_of = s.get("directory","")
                break
    active_str = f"<code>{html.escape(active)}</code>\n<i>{html.escape(title)}</i>\nDir: <code>{html.escape(dir_of)}</code>" if active else "<i>(belum ada / fresh)</i>"
    # anti-spam queue info
    qinfo = ""
    try:
        q = _ACTIVE_JOBS.get(update.effective_chat.id)
        if q:
            qinfo = f"\n⏳ Job aktif: <i>sedang streaming</i> — /cancel untuk batal"
    except Exception:
        pass
    await update.message.reply_text(
        f"📊 <b>Status</b>\nWORK_DIR: <code>{html.escape(RUNTIME_WORK_DIR)}</code>\nEnv WORK_DIR: <code>{html.escape(WORK_DIR)}</code>\nModel: <code>{html.escape(RUNTIME_MODEL)}</code>\nSession aktif: {active_str}{qinfo}\nTotal sesi di WORK_DIR: <b>{len(sessions)}</b>\n\n<i>Kirim pesan → lanjut session aktif. /sessions untuk ganti.</i>",
        parse_mode=ParseMode.HTML,
    )

# === SESSION MGMT: rename / delete / fork / share / export ===
async def rename_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak.")
        return
    active = get_active_session(update.effective_chat.id)
    if not active:
        await update.message.reply_text("❌ Tidak ada session aktif. /sessions dulu.", parse_mode=ParseMode.HTML)
        return
    title = " ".join(context.args or []).strip()
    if not title:
        await update.message.reply_text("Gunakan: <code>/rename Judul baru session</code>", parse_mode=ParseMode.HTML)
        return
    # opencode session rename via CLI? fallback: use opencode session ... try
    # opencode doesn't have explicit rename; we simulate by sending a prompt to rename? Instead call opencode session update if exists
    # Try generic: opencode session --help has no rename, so we do file-based? Just set via opencode run with --title?
    # Simplest: run opencode run with --session and --title to rename
    try:
        proc = await asyncio.create_subprocess_exec("opencode", "run", f"rename session title to: {title}", "--session", active, "--dir", RUNTIME_WORK_DIR, "--title", title, "--format", "json", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await asyncio.wait_for(proc.communicate(), timeout=20)
        await update.message.reply_text(f"✅ Rename dikirim → <code>{html.escape(active)}</code>\nJudul: <i>{html.escape(title)}</i>\n<i>Cek /sessions untuk verifikasi (mungkin perlu 2s).</i>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Rename gagal: {html.escape(str(e))}", parse_mode=ParseMode.HTML)

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak.")
        return
    target = (context.args[0] if context.args else "").strip()
    active = get_active_session(update.effective_chat.id)
    sid = target if target.startswith("ses_") else active
    if not sid:
        await update.message.reply_text("Gunakan: <code>/delete ses_xxx</code> atau <code>/delete</code> untuk hapus session aktif", parse_mode=ParseMode.HTML)
        return
    try:
        proc = await asyncio.create_subprocess_exec("opencode", "session", "delete", sid, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0:
            if sid == active:
                clear_active_session(update.effective_chat.id)
            await update.message.reply_text(f"🗑️ Session dihapus: <code>{html.escape(sid)}</code>", parse_mode=ParseMode.HTML)
        else:
            err = (stderr or stdout).decode("utf-8", errors="replace")[:500]
            await update.message.reply_text(f"❌ Gagal hapus: {html.escape(err)}", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Error delete: {html.escape(str(e))}", parse_mode=ParseMode.HTML)

async def fork_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("Akses ditolak.")
        return
    active = get_active_session(update.effective_chat.id)
    if not active:
        await update.message.reply_text("❌ Tidak ada session aktif untuk di-fork.", parse_mode=ParseMode.HTML)
        return
    # fork = set active with --fork on next run; for now just inform and create fork marker
    # Use opencode run --session --fork
    try:
        prompt = " ".join(context.args) if context.args else "fork this session"
        proc = await asyncio.create_subprocess_exec("opencode", "run", prompt, "--session", active, "--fork", "--dir", RUNTIME_WORK_DIR, "--format", "json", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        raw = stdout.decode("utf-8", errors="replace")
        # extract new sessionID from json lines
        new_sid = None
        for line in raw.splitlines():
            try:
                j=json.loads(line)
                sid=j.get("sessionID") or j.get("part",{}).get("sessionID")
                if sid and sid.startswith("ses_") and sid != active:
                    new_sid = sid
            except: pass
        if new_sid:
            set_active_session(update.effective_chat.id, new_sid)
            await update.message.reply_text(f"🍴 <b>Forked</b> {html.escape(active[:12])} → <code>{html.escape(new_sid)}</code>\n<i>Session baru aktif.</i>", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"✅ Fork dikirim (cek /sessions, active tetap {html.escape(active[:8])})", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Fork gagal: {html.escape(str(e))}", parse_mode=ParseMode.HTML)

async def share_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("Akses ditolak.")
        return
    active = get_active_session(update.effective_chat.id)
    if not active:
        await update.message.reply_text("❌ Tidak ada session aktif.", parse_mode=ParseMode.HTML)
        return
    try:
        proc = await asyncio.create_subprocess_exec("opencode", "run", "share session", "--session", active, "--share", "--dir", RUNTIME_WORK_DIR, "--format", "json", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=20)
        raw = stdout.decode("utf-8", errors="replace")[:2000]
        await update.message.reply_text(f"🔗 <b>Share</b> → <code>{html.escape(active)}</code>\n<pre>{html.escape(raw[:1000])}</pre>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Share gagal: {html.escape(str(e))}", parse_mode=ParseMode.HTML)

async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("Akses ditolak.")
        return
    active = get_active_session(update.effective_chat.id)
    if not active:
        await update.message.reply_text("❌ Tidak ada session aktif.", parse_mode=ParseMode.HTML)
        return
    try:
        # try opencode session export or get
        for cmd in [["opencode","session","export",active,"--dir",RUNTIME_WORK_DIR],["opencode","session","get",active,"--dir",RUNTIME_WORK_DIR]]:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            if proc.returncode == 0 and stdout:
                raw = stdout.decode("utf-8", errors="replace")
                # send as document
                import tempfile
                tmp = Path(tempfile.gettempdir()) / f"session_{active[:8]}.md"
                tmp.write_text(raw[:500000], encoding="utf-8")
                await update.message.reply_document(document=open(tmp,"rb"), filename=f"{active}.md", caption=f"📄 Export <code>{html.escape(active)}</code>", parse_mode=ParseMode.HTML)
                return
        await update.message.reply_text("❌ Export tidak tersedia di CLI ini. Coba <code>opencode session list --format json</code> manual.", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ Export gagal: {html.escape(str(e))}", parse_mode=ParseMode.HTML)

async def switch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.callback_query.answer("Akses ditolak", show_alert=True)
        return
    q = update.callback_query
    data = (q.data or "")
    if not data.startswith("sw:"):
        await q.answer()
        return
    payload = data[3:]
    # pagination
    if payload.startswith("page:"):
        try:
            page = int(payload.split(":",1)[1])
        except:
            page = 0
        await q.answer(f"Halaman {page+1}")
        sessions = await fetch_sessions(limit=100)
        active = get_active_session(update.effective_chat.id)
        html_body = build_sessions_html(sessions, active, page=page, page_size=10)
        kb = build_sessions_keyboard(sessions, active, page=page, page_size=10)
        header = f"📂 <b>Sessions di WORK_DIR</b> • <code>{html.escape(RUNTIME_WORK_DIR)}</code>\nAktif: <code>{html.escape(active) if active else '-'}</code> • Hal {page+1}\n— — —\n"
        text = header + html_body + f"\n\n<i>Tap nomor untuk switch.</i>"
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception as e:
            log.debug(f"page edit fail {e}")
        return
    if payload == "workdir":
        await q.answer("Lihat /workdir")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Gunakan <code>/workdir</code> untuk ganti project. Contoh: <code>/workdir C:\\Project\\Baru</code>", parse_mode=ParseMode.HTML)
        return
    if payload == "refresh":
        await q.answer("Refresh...")
        sessions = await fetch_sessions(limit=100)
        active = get_active_session(update.effective_chat.id)
        html_body = build_sessions_html(sessions, active, page=0, page_size=10)
        kb = build_sessions_keyboard(sessions, active, page=0, page_size=10)
        header = f"📂 <b>Sessions di WORK_DIR</b> • <code>{html.escape(RUNTIME_WORK_DIR)}</code>\nAktif: <code>{html.escape(active) if active else '-'}</code>\n— — —\n"
        text = header + html_body + f"\n\n<i>Tap nomor untuk switch.</i>"
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception as e:
            log.debug(f"refresh edit fail {e}")
        return
    if payload == "new":
        clear_active_session(update.effective_chat.id)
        await q.answer("Session di-reset → pesan baru = fresh")
        try:
            await q.edit_message_text("🆕 <b>Session di-reset</b>\nPesan selanjutnya = session baru.\n\n<i>Balik via /sessions kapan saja.</i>", parse_mode=ParseMode.HTML)
        except: pass
        await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ Reset — kirim pesan untuk mulai session baru.", parse_mode=ParseMode.HTML)
        return
    if payload == "cancel":
        cid = update.effective_chat.id
        job = _ACTIVE_JOBS.get(cid)
        proc = _JOB_PROCS.get(cid)
        if proc and proc.returncode is None:
            try:
                proc.kill()
                await q.answer("Job dibatalkan")
                await q.edit_message_text("⏹️ <b>Job dibatalkan</b> oleh user.", parse_mode=ParseMode.HTML)
            except Exception as e:
                await q.answer(f"Gagal cancel: {e}")
        elif job:
            try:
                job.cancel()
                await q.answer("Job dibatalkan")
            except Exception:
                pass
        else:
            await q.answer("Tidak ada job aktif")
        return
    # payload = session id
    sid = payload
    set_active_session(update.effective_chat.id, sid)
    await q.answer(f"Switched → {sid[-8:]}")
    sessions = await fetch_sessions(limit=100)
    active = sid
    html_body = build_sessions_html(sessions, active, page=0, page_size=10)
    kb = build_sessions_keyboard(sessions, active, page=0, page_size=10)
    header = f"📂 <b>Sessions di WORK_DIR</b> • <code>{html.escape(RUNTIME_WORK_DIR)}</code>\nAktif: <code>{html.escape(active)}</code> ✅\n— — —\n"
    text = header + html_body + f"\n\n<i>✅ Aktif → kirim pesan untuk lanjut konteks.</i>"
    try:
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except Exception as e:
        log.debug(f"switch edit fail {e}")
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ <b>Switched</b> → <code>{html.escape(sid)}</code>\n<i>Kirim pesan untuk lanjut konteks session ini.</i>", parse_mode=ParseMode.HTML)
    log.info(f"Callback switch {update.effective_user.id} -> {sid}")

# === OBSERVABILITY: health / logs / metrics ===
_START_TIME = time.time()
async def health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("Akses ditolak.")
        return
    uptime = int(time.time() - _START_TIME)
    h, m = divmod(uptime, 3600)
    m, s = divmod(m, 60)
    sessions = await fetch_sessions(limit=100)
    active = get_active_session(update.effective_chat.id)
    qsize = len(_QUEUE)
    jobs = len([t for t in _ACTIVE_JOBS.values() if not t.done()]) if _ACTIVE_JOBS else 0
    await update.message.reply_text(
        f"💚 <b>Health OK</b> • uptime <code>{h}h {m}m {s}s</code>\n"
        f"WORK_DIR: <code>{html.escape(RUNTIME_WORK_DIR)}</code>\n"
        f"Model: <code>{html.escape(RUNTIME_MODEL)}</code>\n"
        f"Sesi di WORK_DIR: <b>{len(sessions)}</b> • aktif: <code>{html.escape(active) if active else '-'}</code>\n"
        f"Queue: {qsize} • jobs: {jobs} • Allowed: {len(ALLOWED_USER_IDS)}\n"
        f"Mode: <code>{'webhook' if WEBHOOK_URL else 'polling'}</code>",
        parse_mode=ParseMode.HTML,
    )

async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("Akses ditolak.")
        return
    n = 20
    if context.args and context.args[0].isdigit():
        try: n = max(5, min(50, int(context.args[0])))
        except: n = 20
    log_path = Path(os.getenv("TEMP", str(Path(__file__).parent))) / "telegram-bridge" / "bridge.log"
    # fallback child_stderr
    alt = Path(os.getenv("TEMP", str(Path(__file__).parent))) / "telegram-bridge" / "child_stderr.log"
    content = ""
    for p in [log_path, alt]:
        if p.exists():
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                tail = "\n".join(lines[-n:])
                # mask token
                if BOT_TOKEN:
                    tail = tail.replace(BOT_TOKEN, "***BOT_TOKEN***")
                content = tail
                break
            except Exception as e:
                content = f"Gagal baca log: {e}"
    if not content:
        content = "(log kosong / tidak ditemukan)"
    # mask token again
    if BOT_TOKEN:
        content = content.replace(BOT_TOKEN, "***BOT_TOKEN***")
    await update.message.reply_text(f"📜 <b>Logs tail {n}</b>:\n<pre>{html.escape(content[-3500:])}</pre>", parse_mode=ParseMode.HTML)

async def allow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global ALLOWED_USER_IDS
    if not is_allowed(update):
        await update.message.reply_text("Akses ditolak.")
        return
    args = context.args or []
    if not args:
        lst = ", ".join(f"<code>{x}</code>" for x in sorted(ALLOWED_USER_IDS))
        await update.message.reply_text(f"👥 <b>Allowed</b>: {lst}\n\nGunakan: <code>/allow add 123456</code> | <code>/allow remove 123456</code>", parse_mode=ParseMode.HTML)
        return
    if args[0] == "add" and len(args) >= 2 and args[1].isdigit():
        ALLOWED_USER_IDS.add(int(args[1]))
        await update.message.reply_text(f"✅ Added <code>{args[1]}</code> — total {len(ALLOWED_USER_IDS)}", parse_mode=ParseMode.HTML)
        log.info(f"Allow add {args[1]} by {update.effective_user.id}")
        return
    if args[0] == "remove" and len(args) >= 2 and args[1].isdigit():
        ALLOWED_USER_IDS.discard(int(args[1]))
        await update.message.reply_text(f"✅ Removed <code>{args[1]}</code>", parse_mode=ParseMode.HTML)
        log.info(f"Allow remove {args[1]} by {update.effective_user.id}")
        return
    await update.message.reply_text("Gunakan: <code>/allow add 123456</code> atau <code>/allow remove 123456</code>", parse_mode=ParseMode.HTML)

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("Akses ditolak.")
        return
    cid = update.effective_chat.id
    proc = _JOB_PROCS.get(cid)
    job = _ACTIVE_JOBS.get(cid)
    if proc and proc.returncode is None:
        try:
            proc.kill()
            await update.message.reply_text("⏹️ Job dibatalkan (proc killed).", parse_mode=ParseMode.HTML)
            return
        except Exception as e:
            await update.message.reply_text(f"Gagal cancel proc: {html.escape(str(e))}", parse_mode=ParseMode.HTML)
            return
    if job and not job.done():
        job.cancel()
        await update.message.reply_text("⏹️ Job dibatalkan.", parse_mode=ParseMode.HTML)
        return
    await update.message.reply_text("Tidak ada job aktif untuk dibatalkan.", parse_mode=ParseMode.HTML)


async def self_watch():
    """Watch mtime + .restart flag dengan debounce 4s — cegah restart beruntun saat batch-edit."""
    if not ENABLE_AUTO_RESTART:
        log.info("Self-watch DISABLED (ENABLE_AUTO_RESTART=0) — pakai /restart manual")
        while True:
            await asyncio.sleep(3600)
    global _SELF_MTIME
    log.info(f"Self-watch aktif: {_SELF_PATH} mtime={_SELF_MTIME} flag={_RESTART_FLAG}")
    pending_change = None
    while True:
        await asyncio.sleep(1.5)
        try:
            if _RESTART_FLAG.exists() or _RESTART_FLAG2.exists():
                log.info("Restart flag detected — exiting for loop restart")
                try:
                    _RESTART_FLAG.unlink(missing_ok=True)
                    _RESTART_FLAG2.unlink(missing_ok=True)
                except:
                    pass
                await asyncio.sleep(1)
                os._exit(0)
            if _SELF_PATH.exists():
                cur = _SELF_PATH.stat().st_mtime
                if cur != _SELF_MTIME:
                    if pending_change is None:
                        pending_change = time.time()
                        log.info(f"Bridge file changed mtime {_SELF_MTIME} -> {cur} — debounce 4s")
                    elif time.time() - pending_change >= 4:
                        log.info(f"Bridge file stable after 4s, auto-restart now (mtime {cur})")
                        await asyncio.sleep(1)
                        os._exit(0)
                else:
                    pending_change = None
        except SystemExit:
            raise
        except Exception as e:
            log.debug(f"self_watch error: {e}")


# === HANDLE generic document & voice (PnP file) ===
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    doc = update.message.document
    if not doc:
        return
    # size check 20MB Bot API
    if doc.file_size and doc.file_size > 20*1024*1024:
        await update.message.reply_text("❌ File >20MB, kompres dulu (Bot API limit).", parse_mode=ParseMode.HTML)
        return
    caption = (update.message.caption or doc.file_name or "analisa file ini").strip()
    tmpdir = Path(os.getenv("TEMP", os.getenv("TMP", str(Path(__file__).parent / "tmp_images")))) / "sparkgram_files"
    tmpdir.mkdir(parents=True, exist_ok=True)
    try:
        file = await context.bot.get_file(doc.file_id)
        dest = tmpdir / f"{doc.file_unique_id}_{Path(doc.file_name or 'file').name.replace(' ', '_')}"
        await file.download_to_drive(str(dest))
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal download file: {html.escape(str(e))}", parse_mode=ParseMode.HTML)
        return
    active_sid = get_active_session(update.effective_chat.id)
    short_model = RUNTIME_MODEL.split("/")[-1]
    sess_hint = f"↔️ <code>{html.escape(active_sid[-8:])}</code>" if active_sid else "🆕 <i>new</i>"
    status_msg = await update.message.reply_text(f"📄 <b>{html.escape(short_model)}</b> {sess_hint} • file {html.escape(dest.name)}\n<code>{html.escape(caption[:120])}</code>", parse_mode=ParseMode.HTML)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    final_text, tool_logs, elapsed, tokens, out_sid = await stream_opencode(caption, status_msg, context.bot, update.effective_chat.id, image_paths=[str(dest)], session_id=active_sid)
    if out_sid and out_sid.startswith("ses_") and out_sid != active_sid:
        set_active_session(update.effective_chat.id, out_sid)
    if final_text.startswith("❌"):
        try: await status_msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        except: await update.message.reply_text(final_text, parse_mode=ParseMode.HTML)
        return
    if not final_text.strip():
        final_text = "(File processed — no text, tools maybe ran)"
        if tool_logs: final_text += "\n\n" + "\n".join(tool_logs)
    tok_str = f" • {tokens.get('output',0)} out / {tokens.get('total',0)} total" if tokens else ""
    sess_str = html.escape(out_sid) if out_sid else (html.escape(active_sid) if active_sid else "new")
    header = f"✅ <b>{html.escape(short_model)} file selesai</b> • {elapsed}s{tok_str}\n<i>{html.escape(RUNTIME_MODEL)}</i> • <code>{sess_str}</code> • 📄 {html.escape(dest.name)}\n" + ("\n".join(tool_logs)+"\n" if tool_logs else "") + "—"*20
    chunks = split_markdown(final_text, header, 3500)
    try: await status_msg.edit_text(chunks[0], parse_mode=ParseMode.HTML)
    except Exception as e:
        plain = re.sub(r"<[^>]+>", "", chunks[0])
        try: await status_msg.edit_text(plain[:3900])
        except: await update.message.reply_text(chunks[0][:3900], parse_mode=ParseMode.HTML if "<" in chunks[0] else None)
    for chunk in chunks[1:]:
        try: await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
        except: await update.message.reply_text(re.sub(r"<[^>]+>", "", chunk)[:3900])
        await asyncio.sleep(0.3)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    voice = update.message.voice or update.message.audio
    if not voice:
        return
    if voice.file_size and voice.file_size > 20*1024*1024:
        await update.message.reply_text("❌ Voice >20MB", parse_mode=ParseMode.HTML)
        return
    tmpdir = Path(os.getenv("TEMP", os.getenv("TMP", str(Path(__file__).parent / "tmp_images")))) / "sparkgram_files"
    tmpdir.mkdir(parents=True, exist_ok=True)
    try:
        file = await context.bot.get_file(voice.file_id)
        ext = Path(file.file_path or "").suffix or ".ogg"
        dest = tmpdir / f"{voice.file_unique_id}{ext}"
        await file.download_to_drive(str(dest))
    except Exception as e:
        await update.message.reply_text(f"❌ Gagal download voice: {html.escape(str(e))}", parse_mode=ParseMode.HTML)
        return
    active_sid = get_active_session(update.effective_chat.id)
    short_model = RUNTIME_MODEL.split("/")[-1]
    sess_hint = f"↔️ <code>{html.escape(active_sid[-8:])}</code>" if active_sid else "🆕 <i>new</i>"
    status_msg = await update.message.reply_text(f"🎙️ <b>{html.escape(short_model)}</b> {sess_hint} • voice {html.escape(dest.name)}\n<i>transcribe via --file</i>", parse_mode=ParseMode.HTML)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    # Note: opencode vision models may not transcribe directly; we pass as file and ask to transcribe
    prompt = "transcribe this voice/audio file and respond accurately in Indonesian; file attached"
    final_text, tool_logs, elapsed, tokens, out_sid = await stream_opencode(prompt, status_msg, context.bot, update.effective_chat.id, image_paths=[str(dest)], session_id=active_sid)
    if out_sid and out_sid.startswith("ses_") and out_sid != active_sid:
        set_active_session(update.effective_chat.id, out_sid)
    if final_text.startswith("❌"):
        try: await status_msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        except: await update.message.reply_text(final_text, parse_mode=ParseMode.HTML)
        return
    if not final_text.strip():
        final_text = "(Voice processed)"
    tok_str = f" • {tokens.get('output',0)} out / {tokens.get('total',0)} total" if tokens else ""
    sess_str = html.escape(out_sid) if out_sid else (html.escape(active_sid) if active_sid else "new")
    header = f"✅ <b>{html.escape(short_model)} voice selesai</b> • {elapsed}s{tok_str}\n<i>{html.escape(RUNTIME_MODEL)}</i> • <code>{sess_str}</code> • 🎙️ {html.escape(dest.name)}\n" + ("\n".join(tool_logs)+"\n" if tool_logs else "") + "—"*20
    chunks = split_markdown(final_text, header, 3500)
    try: await status_msg.edit_text(chunks[0], parse_mode=ParseMode.HTML)
    except: await update.message.reply_text(re.sub(r"<[^>]+>", "", chunks[0])[:3900])
    for chunk in chunks[1:]:
        try: await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
        except: await update.message.reply_text(re.sub(r"<[^>]+>", "", chunk)[:3900])
        await asyncio.sleep(0.3)

# ===== LIVE STREAMING CORE =====
async def stream_opencode(prompt: str, status_msg, bot, chat_id: int, image_paths: list[str] | None = None, session_id: str | None = None):
    """
    Jalankan opencode run --format json dan streaming step-by-step ke Telegram via edit.
    PnP image: jika image_paths ada, kirim via --file (vision-capable model).
    session_id: jika ada, tambahkan --session untuk lanjut konteks (opencode TUI session).
    Return: (final_text, tool_logs, elapsed, tokens, out_session_id)
    """
    cmd = [
        "opencode", "run", prompt,
        "--dir", RUNTIME_WORK_DIR,
        "--format", "json",
        "--model", RUNTIME_MODEL,
        "--auto",
        "--thinking",
    ]
    if session_id:
        cmd.extend(["--session", session_id])
    if image_paths:
        for p in image_paths:
            cmd.extend(["--file", p])
    log.info(f"STREAM PnP: model={RUNTIME_MODEL} dir={RUNTIME_WORK_DIR} session={session_id or 'NEW'} images={len(image_paths) if image_paths else 0} | {' '.join(cmd[:10])}...")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=10 * 1024 * 1024,  # 10 MB — cegah LimitOverrunError untuk JSON line raksasa
    )
    # register for /cancel
    try:
        _JOB_PROCS[chat_id] = proc
    except Exception:
        pass

    assistant_text = ""
    tool_logs = []
    reasoning_active = False
    start_time = time.time()
    last_text_len = 0
    tokens_info = {}
    out_session_id = session_id  # akan di-overwrite dari event sessionID jika ada

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

            # capture sessionID dari event top-level atau part
            sid_evt = event.get("sessionID") or part.get("sessionID") or ""
            if sid_evt and sid_evt.startswith("ses_"):
                out_session_id = sid_evt
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
                short = title.replace(RUNTIME_WORK_DIR, ".").replace("C:\\Users\\Reynboo", "~") if title else ""
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
            return f"❌ Opencode exit {proc.returncode}\n{html.escape(stderr[:1000])}", tool_logs, elapsed, tokens_info, out_session_id

        return assistant_text, tool_logs, elapsed, tokens_info, out_session_id

    except Exception as e:
        anim_task.cancel()
        try:
            await anim_task
        except:
            pass
        log.exception("stream error")
        return f"❌ Error streaming: {html.escape(str(e))}", tool_logs, int(time.time()-start_time), {}, out_session_id


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    if not update.message or not update.message.text:
        return
    prompt = update.message.text.strip()
    if not prompt or prompt.startswith("/"):
        return
    chat_id = update.effective_chat.id
    if FEATURE_QUEUE:
        # rate limit
        now = time.time()
        last = _LAST_MSG_TIME.get(chat_id, 0)
        if now - last < _RATE_LIMIT_SEC:
            await update.message.reply_text(f"⏳ Tunggu {(_RATE_LIMIT_SEC - (now-last)):.1f}s — rate limit anti-spam.", parse_mode=ParseMode.HTML)
            return
        _LAST_MSG_TIME[chat_id] = now
        # queue: if job active, enqueue one
        if chat_id in _ACTIVE_JOBS and not _ACTIVE_JOBS[chat_id].done():
            _QUEUE[chat_id] = prompt
            await update.message.reply_text("📥 Job masih jalan — prompt di-queue (1). Akan dijalankan setelah selesai. /cancel untuk batal.", parse_mode=ParseMode.HTML)
            return
    # Session continuity: ambil active session untuk RUNTIME_WORK_DIR ini
    active_sid = get_active_session(chat_id)
    short_model = RUNTIME_MODEL.split("/")[-1]
    sess_hint = f"↔️ <code>{html.escape(active_sid[-8:])}</code>" if active_sid else "🆕 <i>new</i>"
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⏹ Batal", callback_data="sw:cancel")]])
    status_msg = await update.message.reply_text(
        f"⏳ <b>{html.escape(short_model)}</b> {sess_hint} • mulai 0s\n<code>{html.escape(prompt[:80])}</code>\n<i>{html.escape(RUNTIME_MODEL)} • {html.escape(Path(RUNTIME_WORK_DIR).name)}</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_kb,
    )
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    # track job
    async def _run():
        return await stream_opencode(prompt, status_msg, context.bot, chat_id, session_id=active_sid)
    task = asyncio.create_task(_run())
    _ACTIVE_JOBS[chat_id] = task
    try:
        final_text, tool_logs, elapsed, tokens, out_sid = await task
    except asyncio.CancelledError:
        await status_msg.edit_text("⏹️ Dibatalkan.", parse_mode=ParseMode.HTML)
        _ACTIVE_JOBS.pop(chat_id, None)
        return
    finally:
        _ACTIVE_JOBS.pop(chat_id, None)
        _JOB_PROCS.pop(chat_id, None)
    # Auto-persist via _run already? need capture out_sid
    # Re-await already done, now handle out_sid via result above
    # final_text etc already have out_sid
    # Auto-persist session: jika baru terbuat, simpan jadi active
    if out_sid and out_sid.startswith("ses_"):
        # jika belum ada active atau berbeda, update
        if out_sid != active_sid:
            set_active_session(update.effective_chat.id, out_sid)
            log.info(f"Auto-persist session {update.effective_chat.id} -> {out_sid}")

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

    # Buat header cantik — PnP model + session
    tok_str = ""
    if tokens:
        tok_str = f" • {tokens.get('output',0)} tok out / {tokens.get('total',0)} total"
    short_model = RUNTIME_MODEL.split("/")[-1]
    sess_str = html.escape(out_sid) if 'out_sid' in locals() and out_sid else (html.escape(active_sid) if active_sid else "new")
    header = f"✅ <b>{html.escape(short_model)} selesai</b> • {elapsed}s{tok_str}\n<i>{html.escape(RUNTIME_MODEL)}</i> • <code>{sess_str}</code>\n"
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
    # queue dispatch after finish
    if chat_id in _QUEUE:
        queued = _QUEUE.pop(chat_id, None)
        if queued:
            await update.message.reply_text(f"▶️ Menjalankan antrean: <code>{html.escape(queued[:80])}</code>", parse_mode=ParseMode.HTML)
            # re-enter via fresh call (copy update)
            try:
                update.message.text = queued
                await handle_message(update, context)
            except Exception as e:
                log.warning(f"queue dispatch fail: {e}")


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """PnP image handler — download foto dari Telegram, teruskan ke opencode vision via --file."""
    if not is_allowed(update):
        await update.message.reply_text(f"Akses ditolak. ID kamu: {update.effective_user.id}")
        return
    # Ambil file terbesar (photo[-1]) atau document image
    photo = None
    if update.message.photo:
        photo = update.message.photo[-1]
    elif update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith("image/"):
        photo = update.message.document
    else:
        await update.message.reply_text("Kirim foto sebagai Photo (bukan file) atau Document image.")
        return

    # Validasi ukuran Bot API 20MB
    if hasattr(photo, "file_size") and photo.file_size and photo.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ Gambar >20MB, kompres dulu (Bot API limit 20MB).")
        return

    caption = (update.message.caption or "").strip()
    if not caption:
        caption = "jelaskan gambar ini secara detail: apa isinya, objek utama, warna, konteks, dan insight relevan"

    # Download
    tmpdir = Path(os.getenv("TEMP", os.getenv("TMP", str(Path(__file__).parent / "tmp_images")))) / "sparkgram_images"
    tmpdir.mkdir(parents=True, exist_ok=True)
    try:
        file = await context.bot.get_file(photo.file_id)
        ext = Path(file.file_path or "").suffix or ".jpg"
        if not ext or len(ext) > 5:
            ext = ".jpg"
        dest = tmpdir / f"{photo.file_unique_id}{ext}"
        await file.download_to_drive(str(dest))
    except Exception as e:
        log.exception("download image fail")
        await update.message.reply_text(f"❌ Gagal download gambar: {html.escape(str(e))}", parse_mode=ParseMode.HTML)
        return

    active_sid = get_active_session(update.effective_chat.id)
    short_model = RUNTIME_MODEL.split("/")[-1]
    sess_hint = f"↔️ <code>{html.escape(active_sid[-8:])}</code>" if active_sid else "🆕 <i>new</i>"
    status_msg = await update.message.reply_text(
        f"🖼️ <b>{html.escape(short_model)}</b> {sess_hint} • menerima gambar {html.escape(dest.name)}\n<code>{html.escape(caption[:120])}</code>\n<i>vision via --file</i>",
        parse_mode=ParseMode.HTML,
    )
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Stream opencode dengan image attach + session continuity
    final_text, tool_logs, elapsed, tokens, out_sid = await stream_opencode(caption, status_msg, context.bot, update.effective_chat.id, image_paths=[str(dest)], session_id=active_sid)
    if out_sid and out_sid.startswith("ses_") and out_sid != active_sid:
        set_active_session(update.effective_chat.id, out_sid)
        log.info(f"Auto-persist vision session {update.effective_chat.id} -> {out_sid}")

    if final_text.startswith("❌"):
        try:
            await status_msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        except:
            await update.message.reply_text(final_text, parse_mode=ParseMode.HTML)
        return
    if not final_text or not final_text.strip():
        final_text = "(Vision tidak mengembalikan teks, tapi tools mungkin sudah dijalankan)"
        if tool_logs:
            final_text += "\n\n" + "\n".join(tool_logs)

    tok_str = ""
    if tokens:
        tok_str = f" • {tokens.get('output',0)} tok out / {tokens.get('total',0)} total"
    sess_str = html.escape(out_sid) if 'out_sid' in locals() and out_sid else (html.escape(active_sid) if active_sid else "new")
    header = f"✅ <b>{html.escape(short_model)} vision selesai</b> • {elapsed}s{tok_str}\n<i>{html.escape(RUNTIME_MODEL)}</i> • <code>{sess_str}</code> • 🖼️ {html.escape(dest.name)}\n"
    if tool_logs:
        header += "\n".join(tool_logs) + "\n"
    header += "—" * 20

    chunks = split_markdown(final_text, header, 3500)
    try:
        await status_msg.edit_text(chunks[0], parse_mode=ParseMode.HTML)
    except Exception as e:
        log.warning(f"vision final edit fail: {e}")
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
    # Cleanup opsional: jangan hapus langsung biar bisa audit, tapi batasi 50 file
    try:
        files = sorted(tmpdir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[50:]:
            old.unlink(missing_ok=True)
    except:
        pass



async def cleanup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("Akses ditolak.")
        return
    days = 30
    if context.args and context.args[0].isdigit():
        try: days = max(1, min(365, int(context.args[0])))
        except: days = 30
    dry = len(context.args) > 1 and context.args[1] == "dry"
    sessions = await fetch_sessions(limit=100)
    import time
    cutoff = int(time.time()*1000) - days*24*3600*1000
    to_del = [s for s in sessions if (s.get("updated") or 0) < cutoff]
    if not to_del:
        await update.message.reply_text(f"\u2705 Tidak ada sesi >{days}d (total {len(sessions)}).", parse_mode=ParseMode.HTML)
        return
    if dry:
        body = "\n".join(f"\u2022 <code>{s.get('id')}</code> {__import__('html').escape(s.get('title','')[:40])}" for s in to_del[:15])
        await update.message.reply_text(f"\U0001f9f9 Dry-run {len(to_del)} sesi >{days}d akan dihapus:\n{body}", parse_mode=ParseMode.HTML)
        return
    # confirm keyboard
    kb = __import__('telegram').InlineKeyboardMarkup([[__import__('telegram').InlineKeyboardButton(f"Hapus {len(to_del)}", callback_data=f"clean:{days}"), __import__('telegram').InlineKeyboardButton("Batal", callback_data="clean:cancel")]])
    body = "\n".join(f"\u2022 <code>{s.get('id')[:12]}</code> {__import__('html').escape(s.get('title','')[:30])}" for s in to_del[:10])
    await update.message.reply_text(f"\u26a0\ufe0f Hapus {len(to_del)} sesi >{days}d?\n{body}\n\n/dry untuk simulasi.", parse_mode=ParseMode.HTML, reply_markup=kb)

async def archive_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("Akses ditolak.")
        return
    sessions = await fetch_sessions(limit=100)
    import json, tempfile
    tmp = Path(tempfile.gettempdir()) / f"sessions_{int(__import__('time').time())}.json"
    tmp.write_text(json.dumps(sessions, indent=2, ensure_ascii=False), encoding="utf-8")
    await update.message.reply_document(document=open(tmp,"rb"), filename=tmp.name, caption=f"\U0001f4e6 Archive {len(sessions)} sesi di <code>{__import__('html').escape(RUNTIME_WORK_DIR)}</code>", parse_mode=ParseMode.HTML)

async def cleanup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    if not data.startswith("clean:"):
        return
    payload = data.split(":",1)[1]
    if payload == "cancel":
        await q.answer("Batal")
        try: await q.edit_message_text("Batal cleanup.")
        except: pass
        return
    try: days = int(payload)
    except: days = 30
    await q.answer(f"Menghapus >{days}d...")
    sessions = await fetch_sessions(limit=100)
    import time
    cutoff = int(time.time()*1000) - days*24*3600*1000
    to_del = [s for s in sessions if (s.get("updated") or 0) < cutoff]
    ok = 0
    for s in to_del:
        try:
            proc = await __import__('asyncio').create_subprocess_exec("opencode","session","delete",s.get("id"), stdout=__import__('asyncio').subprocess.PIPE, stderr=__import__('asyncio').subprocess.PIPE)
            await __import__('asyncio').wait_for(proc.communicate(), timeout=10)
            if proc.returncode==0: ok+=1
        except: pass
    try: await q.edit_message_text(f"\u2705 Cleanup selesai: {ok}/{len(to_del)} sesi >{days}d dihapus.")
    except: pass
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"\u2705 {ok} sesi dihapus.", parse_mode=ParseMode.HTML)

def main():
    if not BOT_TOKEN or "AA" not in BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN belum diisi. Isi .env atau env var: TELEGRAM_BOT_TOKEN=xxx")
        return
    import shutil
    if not shutil.which("opencode"):
        print("WARNING: opencode not in PATH — PnP mode fallback ke direct LLM via env MODEL tetap jalan jika opencode tidak ada")

    print(f"PnP Live Bridge jalan. MODEL={RUNTIME_MODEL} (env MODEL={MODEL}) | WORK_DIR={RUNTIME_WORK_DIR} (env {WORK_DIR}) | Allowed={ALLOWED_USER_IDS}")
    print(f"Metode: {'webhook '+WEBHOOK_URL if WEBHOOK_URL else 'polling (dev) — set WEBHOOK_URL untuk prod'} | Port {PORT}")
    print("Live loading: edit tiap 1.1s + spinner. Output: Telegram HTML cantik. /model set provider/model untuk ganti PnP.")
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    async def _post_init(application: Application):
        asyncio.create_task(self_watch())
        log.info(f"Self-watch task started (ENABLE_AUTO_RESTART={ENABLE_AUTO_RESTART})")
        # graceful shutdown log
        try:
            import signal
            for sig in (signal.SIGINT, signal.SIGTERM):
                try: asyncio.get_running_loop().add_signal_handler(sig, lambda: log.info(f"Signal {sig} received"))
                except: pass
        except: pass

    app = Application.builder().token(BOT_TOKEN).post_init(_post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("model", model_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("pwd", pwd_cmd))
    if FEATURE_WORKDIR:
        app.add_handler(CommandHandler("workdir", workdir_cmd))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("restart", restart_cmd))
    if FEATURE_SESSIONS:
        app.add_handler(CommandHandler("sessions", sessions_cmd))
        app.add_handler(CommandHandler("switch", switch_cmd))
    app.add_handler(CommandHandler("new", new_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("rename", rename_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CommandHandler("fork", fork_cmd))
    app.add_handler(CommandHandler("share", share_cmd))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CommandHandler("health", health_cmd))
    app.add_handler(CommandHandler("logs", logs_cmd))
    app.add_handler(CommandHandler("allow", allow_cmd))
    if FEATURE_CLEANUP:
        app.add_handler(CommandHandler("cleanup", cleanup_cmd))
        app.add_handler(CommandHandler("archive", archive_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CallbackQueryHandler(cleanup_callback, pattern=r"^clean:"))
    app.add_handler(CallbackQueryHandler(switch_callback, pattern=r"^sw:"))
    # PnP: vision & files — feature-flagged
    if FEATURE_VOICE:
        app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_image))
    if FEATURE_DOC:
        app.add_handler(MessageHandler(filters.Document.ALL & ~filters.Document.IMAGE, handle_document))
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
