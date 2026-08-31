# Telegram AI Agent Bridge — Lean Python (PydanticAI-ready)
FROM python:3.12-slim
WORKDIR /app
# non-root + health tools
RUN useradd -m bot && apt-get update && apt-get install -y --no-install-recommends curl procps && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot_bridge_live.py bot_bridge.py ./
COPY scripts/ ./scripts/
COPY README.md .env.example ./
RUN chown -R bot:bot /app
USER bot
ENV PYTHONUNBUFFERED=1
# PnP: polling=pgrep, webhook=http
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD sh -c 'if [ -n "$WEBHOOK_URL" ]; then python -c "import urllib.request; urllib.request.urlopen(\"http://localhost:${PORT:-8000}/healthz\", timeout=3)"; else pgrep -f bot_bridge_live.py > /dev/null; fi' || exit 1
# Default polling (dev). Untuk webhook, override CMD ke uvicorn
CMD ["python", "bot_bridge_live.py"]
