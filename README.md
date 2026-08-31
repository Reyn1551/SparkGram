# SparkGram — Telegram AI Bridge

Telegram ↔ AI Agent bridge (Muse Spark 1.2). Streaming `editMessageText` 1s, Markdown → Telegram HTML, PnP model/mode, deploy anywhere.

## Quick Start (PnP — Windows/Linux/macOS/WSL semua sama)

**Windows 1-klik:**
```powershell
powershell -ExecutionPolicy Bypass -File scripts/install.ps1
# atau manual:
git clone https://github.com/Reyn1551/SparkGram.git
cd SparkGram
copy .env.example .env  # isi TELEGRAM_BOT_TOKEN
pip install -r requirements.txt
python bot_bridge_live.py
```

**Linux / macOS / WSL:**
```bash
bash scripts/install.sh
# atau:
git clone https://github.com/Reyn1551/SparkGram.git
cd SparkGram
cp .env.example .env  # isi TELEGRAM_BOT_TOKEN
pip3 install -r requirements.txt
python3 bot_bridge_live.py
```

Polling dev — laptop harus nyala. Test di Telegram: `/start` → `✨ Live Bridge` → `/sessions` tap nomor untuk switch.

**Stabilitas & anti-mati-tiba:**
- `ENABLE_AUTO_RESTART=1` (default) auto-restart debounce 4s; set `0` untuk manual `/restart` saja jika fitur bikin bug.
- Feature flags `FEATURE_WORKDIR/FEATURE_CLEANUP/FEATURE_VOICE/FEATURE_DOC/FEATURE_QUEUE=1` — matikan instant tanpa edit code: `FEATURE_VOICE=0` di `.env` lalu `/restart`.
- `MAX_BACKOFF=5` capped (dulu 60s) — downtime `60s→5s`.
- `RUNTIME_WORK_DIR` per-chat per-dir, cross-platform `/app` ↔ `C:\path`.

## Deploy

**Docker Compose (VPS)**

```bash
docker compose up --build -d
docker compose logs -f bot
```

**Railway**

```bash
railway up
# atau connect GitHub → set TELEGRAM_BOT_TOKEN di Variables
```

**Fly.io**

```bash
fly launch --no-deploy
fly secrets set TELEGRAM_BOT_TOKEN=xxx WEBHOOK_SECRET=xxx
fly deploy
```

`Dockerfile` non-root + `HEALTHCHECK`. `railway.json` & `fly.toml` included.

## Konfigurasi

Semua via `.env`:

```
TELEGRAM_BOT_TOKEN=xxx
MODEL=opencode/muse-spark-1.2-contributor-free
WORK_DIR=/app
ALLOWED_USER_IDS=1925430810
WEBHOOK_URL= # kosong=polling, isi=https://.../webhook untuk prod
# Stabilitas:
ENABLE_AUTO_RESTART=1
FEATURE_WORKDIR=1
FEATURE_SESSIONS=1
FEATURE_CLEANUP=1
FEATURE_VOICE=1
FEATURE_DOC=1
FEATURE_QUEUE=1
FALLBACK_MODEL=groq/llama-3.3-70b-versatile
MAX_BACKOFF=5
```

Ganti model tanpa edit kode: `/model set groq/llama-3.3-70b-versatile`

## Struktur

```
bot_bridge_live.py              # live bridge (streaming, vision, /workdir /sessions /cleanup + queue+cancel)
bot_bridge.py                   # legacy polling sederhana
scripts/run_bridge_loop.ps1     # self-healing runner capped 5s + mutex + watchdog 330s
scripts/install.ps1             # PnP installer Windows 1-klik
scripts/install.sh              # PnP installer Linux/macOS/WSL
scripts/install_autostart.ps1   # installer Task Scheduler + Registry + Startup
Dockerfile / docker-compose.yml / railway.json / fly.toml
.env.example (19 token PnP + feature flags)
riset/telegram-ai-agent-best-practice-2026-08-30.md
```

## Catatan Teknis

- Polling: dev <10k user, Webhook: prod (HTTPS + secret_token + /healthz)
- Streaming: throttle 1.1s + spinner, chunk aman di boundary `pre`/`code`
- Formatter: `md_to_telegram_html()` + `split_markdown()` — cegah `LimitOverrunError` & broken tag
- Autostart: Task Scheduler (HIGHEST) → fallback Registry Run → Startup LNK, watchdog 330s

## Autostart Windows

```powershell
# install (butuh Admin sekali untuk Task Scheduler)
.\scripts\install_autostart.ps1
# uninstall
.\scripts\install_autostart.ps1 -Uninstall
# cek log
Get-Content $env:TEMP\telegram-bridge\bridge.log -Tail 30
```

## Lisensi

MIT
