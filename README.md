# SparkGram

# Telegram AI Agent Bridge — Muse Spark 1.2 Live (git clone ready)

Live bridge Telegram ↔ AI Agent dengan streaming 1s + output HTML cantik. Siap `git clone` dan deploy dimana aja (Railway/Render/Fly/VPS/Docker).

## Quick Start (git clone anywhere)

```bash
git clone https://github.com/Reyn1551/telegram-opencode-bridge.git
cd telegram-opencode-bridge
cp .env.example .env  # isi TELEGRAM_BOT_TOKEN
python -m pip install -r requirements.txt
python bot_bridge_live.py  # polling dev → laptop harus nyala
```

Test di Telegram `@Env_OC_BOT` → kirim `halo`.

## Deploy

### Docker Compose (VPS / lokal prod)
```bash
docker compose up --build -d
docker compose logs -f bot
```

### Railway (webhook lean)
```bash
railway up  # auto set RAILWAY_PUBLIC_DOMAIN → setWebhook
# Atau connect GitHub → auto deploy, set TELEGRAM_BOT_TOKEN di Variables
```

### Fly.io
```bash
fly launch --no-deploy
fly secrets set TELEGRAM_BOT_TOKEN=xxx WEBHOOK_SECRET=xxx
fly deploy
```

### Render / VPS
`Dockerfile` sudah non-root + HEALTHCHECK `/healthz` (Railway `railway.json`, Fly `fly.toml` included).

## Konsep (sesuai riset 2026-08-30)

- **Polling vs Webhook:** polling untuk dev (<10k user), webhook prod (HTTPS 443 + `secret_token` + `/healthz`)
- **Streaming:** `editMessageText` throttle 1s + spinner `⠋⠙` (DM bisa `sendMessageDraft` Bot API 9.5)
- **HTML:** Markdown → Telegram HTML (`<b>`, `<code>`, `<pre>`, `<a>`) via `md_to_telegram_html()`
- **Fixes:** `limit=10MB` + `iter_lines()` cegah `LimitOverrunError`, `split_markdown()` cegah `Can't find end tag code` (penyebab stuck 42s)

## Struktur

- `bot_bridge_live.py` — LIVE bridge (muse-spark terkunci, streaming, HTML)
- `bot_bridge.py` — legacy polling sederhana
- `Dockerfile` / `docker-compose.yml` / `railway.json` / `fly.toml` — deploy anywhere
- `.env.example` — env template
- `riset/telegram-ai-agent-best-practice-2026-08-30.md` — laporan riset multi-agent penuh

## Ganti Model / WORK_DIR

```python
# bot_bridge_live.py:18,19
MODEL = "opencode/muse-spark-1.2-contributor-free"
WORK_DIR = r"D:\Riset\HyperSpectral"
```

## Roadmap

Lihat laporan `riset/telegram-ai-agent-best-practice-2026-08-30.md` Hari 2-7 untuk migrasi PydanticAI `Agent.run_stream()`.

## Lisensi

MIT — siap fork.
