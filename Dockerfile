# Telegram AI Agent Bridge — Lean Python (PydanticAI-ready)
FROM python:3.12-slim
WORKDIR /app
# non-root
RUN useradd -m bot && apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot_bridge_live.py bot_bridge.py ./
# opencode CLI tidak di-bundle (pakai PydanticAI di image ini) — untuk opencode mode, mount binary atau pakai agent.py
COPY README.md .env.example ./
RUN chown -R bot:bot /app
USER bot
ENV PYTHONUNBUFFERED=1
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz', timeout=3)" || exit 1
# Default polling (dev). Untuk webhook, override CMD ke uvicorn
CMD ["python", "bot_bridge_live.py"]
