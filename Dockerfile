# SparkGram — High-Performance Telegram AI Remote Dev Companion
FROM python:3.12-slim

WORKDIR /app

# Install tini for deterministic PID 1 zombie reaping + health inspection tools
RUN apt-get update && apt-get install -y --no-install-recommends tini curl procps && rm -rf /var/lib/apt/lists/*
RUN useradd -m sparkgram

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY sparkgram/ ./sparkgram/
COPY bot_bridge_live.py bot_bridge.py ./
COPY scripts/ ./scripts/
COPY README.md .env.example ./

RUN chown -R sparkgram:sparkgram /app
USER sparkgram
ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD sh -c 'if [ -n "$WEBHOOK_URL" ]; then python -c "import urllib.request; urllib.request.urlopen(\"http://localhost:${PORT:-8000}/healthz\", timeout=3)"; else pgrep -f "sparkgram" > /dev/null || pgrep -f "python" > /dev/null; fi' || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "sparkgram"]
