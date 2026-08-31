#!/usr/bin/env bash
# SparkGram PnP Installer — Linux / macOS / WSL / Docker host
set -e
REPO="https://github.com/Reyn1551/SparkGram.git"
DIR="${1:-$HOME/telegram-opencode-bridge}"
echo "=== SparkGram PnP Install (Linux) ==="
if ! command -v git >/dev/null; then echo "git belum ada"; exit 1; fi
if ! command -v python3 >/dev/null; then echo "python3 belum ada"; exit 1; fi
if [ -d "$DIR" ]; then echo "Dir $DIR sudah ada, update..."; cd "$DIR"; git pull; else git clone "$REPO" "$DIR"; cd "$DIR"; fi
[ -f .env ] || { cp .env.example .env; echo ".env dibuat — isi TELEGRAM_BOT_TOKEN!"; ${EDITOR:-nano} .env; }
pip3 install --break-system-packages -r requirements.txt 2>/dev/null || pip3 install -r requirements.txt
echo "=== Test opencode ==="
opencode --version || echo "opencode belum ada — install via https://opencode.ai"
echo "=== Start bridge ==="
echo "Jalankan: python3 bot_bridge_live.py  atau  ./scripts/run_bridge_loop.ps1 (pwsh)"
echo "Cek di Telegram: /start  /sessions  /workdir"
echo "Logs: /tmp/telegram-bridge/bridge.log"
read -p "Jalankan bridge sekarang? (y/n) " ans
if [ "$ans" = "y" ]; then
  if command -v pwsh >/dev/null; then pwsh ./scripts/run_bridge_loop.ps1
  else python3 bot_bridge_live.py
  fi
fi
