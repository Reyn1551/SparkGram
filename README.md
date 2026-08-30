# SparkGram — Telegram AI Bridge

Telegram ↔ AI Agent bridge (Muse Spark 1.2). Streaming `editMessageText` 1s, Markdown → Telegram HTML, PnP model/mode, deploy anywhere.

## Quick Start

```bash
git clone https://github.com/Reyn1551/SparkGram.git
cd SparkGram
cp .env.example .env  # isi TELEGRAM_BOT_TOKEN
python -m pip install -r requirements.txt
python bot_bridge_live.py
```

Polling dev — laptop harus nyala. Test di Telegram kirim `halo`.

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
```

Ganti model tanpa edit kode: `/model set groq/llama-3.3-70b-versatile`

## Struktur

```
bot_bridge_live.py              # live bridge (streaming, vision, /model, /restart)
bot_bridge.py                   # legacy polling sederhana
scripts/run_bridge_loop.ps1     # self-healing runner (Windows autostart)
scripts/install_autostart.ps1   # installer Task Scheduler + Registry + Startup
Dockerfile / docker-compose.yml / railway.json / fly.toml
.env.example
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
