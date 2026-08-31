# SparkGram

<p align="center">
  <a href="README.md">🇮🇩 Bahasa Indonesia</a> • <a href="README_EN.md">🇬🇧 English</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Telegram_Bot_API-7.3+-2CA5E0?style=flat-square&logo=telegram&logoColor=white" />
  <img src="https://img.shields.io/badge/Tests-39_Passed-44cc11?style=flat-square&logo=pytest&logoColor=white" />
  <img src="https://img.shields.io/badge/Platform-Windows_|_Linux_|_macOS-24292e?style=flat-square" />
  <img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" />
</p>

SparkGram is a lightweight Telegram bridge that lets you run and control your local AI coding assistant (such as OpenCode) directly from Telegram chat on your mobile phone or desktop.

---

## 🎯 How It Works

```
[ Telegram Chat ] ──(Prompt / Voice / Photo)──> [ SparkGram Bridge ]
                                                        │
                                                        ▼
[ Mobile / Desktop ] <──(Streaming HTML / Cards)─ [ Subprocess Engine ]
                                                        │
                                                        ▼
                                                [ Local Workspace / Git ]
```

With SparkGram, you can:
- Send coding prompts, debug requests, and code reviews straight from Telegram.
- Watch live streaming output without blocking the chat message queue.
- Switch AI models (Spark, Groq, DeepSeek, Claude, etc.) with 1-tap inline buttons.
- Send error screenshots or terminal captures with attached captions for instant analysis.
- Monitor host machine hardware metrics (CPU, RAM, Disk, GPU Temperature, and Battery).

---

## 🚀 Quick Setup

### Prerequisites:
- Python 3.10 or higher
- An AI coding CLI installed (e.g. [OpenCode](https://github.com/opencode-ai/opencode))
- A Telegram Bot token from [@BotFather](https://t.me/BotFather)

### 1. Clone & Install Dependencies

```bash
git clone https://github.com/Reyn1551/SparkGram.git
cd SparkGram
pip install -e .
```

### 2. Configure Environment

Create a `.env` file in the root directory:

```env
TELEGRAM_BOT_TOKEN="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
ALLOWED_USER_IDS="1925430810"
WORK_DIR="C:\Path\To\Your\Project"
MODEL="opencode/muse-spark-1.2-contributor-free"
GROQ_API_KEY="" # Optional, for voice transcription support
```

> **Security Note:** Always restrict `ALLOWED_USER_IDS` to your own Telegram User ID to prevent unauthorized terminal execution. Send `/id` to your bot to find your ID.

### 3. Run the Bot

```bash
# Run as Python module
python -m sparkgram

# Or run the live supervisor loop (with auto-reloading watchdog)
python bot_bridge_live.py
```

---

## 📱 Key Features

### 1. Clean Chat Typography (Mobile & Desktop)
- **Collapsible Cards (`<blockquote expandable>`)**: Long thinking traces, git diffs, and terminal outputs fold into neat accordions to prevent mobile screen clutter.
- **Syntax Highlighting**: Code blocks are automatically formatted with proper language tags (`<pre><code class="language-xyz">`).
- **Clear Status Badges**: Finished messages clearly indicate completion (`✅ Selesai (Completed)`) along with execution time and timestamps.

### 2. Safe Process Management (Zero Zombies)
- Uses Win32 Job Objects on Windows and POSIX process groups on Linux/macOS to ensure child process trees are cleanly terminated whenever `/cancel` or the `[🛑 Batalkan Job]` button is triggered.

### 3. Telegram Rate Limiter & Tag Balancer
- Implements a *2-Tier Token Bucket* (Global 28 req/s, Chat 1.0–1.2 req/s) and a stateful HTML tag balancer to eliminate `HTTP 429 Too Many Requests` and `HTTP 400 Bad Request` formatting errors.

### 4. Host Hardware Telemetry (`/health`)
- Remotely monitors CPU load, RAM usage, Disk C: space, NVIDIA GPU temperature, and laptop battery/charger state.

---

## 🕹️ Telegram Command Reference

| Command | Description |
|---|---|
| `/start`, `/help` | Displays usage guide and bot status |
| `/model` | Opens interactive 1-tap AI model switcher menu |
| `/sessions` | Lists and switches between previous conversation sessions |
| `/new` | Starts a fresh session with clean context |
| `/workdir [path]` | Views or changes active working directory per chat |
| `/status` | Checks whether the bot is actively executing or idle |
| `/health` | Displays host hardware telemetry (CPU, RAM, GPU, Battery) |
| `/logs [n]` | Views recent log lines from the background bridge |
| `/cancel` | Force-stops the active coding task and cleans up sub-processes |
| `/id` | Displays your Telegram User ID and Chat ID |

---

## 📁 Repository Structure (`sparkgram/`)

```
sparkgram/
├── bot/                 # Telegram handlers (commands, callbacks, media, messages)
├── core/                # Session state persistence and model registries
├── engine/              # Subprocess execution, process tree management, stream reader
├── ratelimit/           # Token bucket rate limiting and flood protection
├── formatters/          # Markdown to Telegram HTML conversion and tag balancing
├── supervisor/          # File modification watchdog with debounced reloading
├── adapters/            # OpenCode CLI and Groq Whisper adapters
└── utils/               # System health monitors and sensitive log masking
```

---

## 🧪 Automated Testing

The entire core codebase is tested using `pytest`:

```bash
pytest -v tests/
```

Test coverage includes:
- HTML tag balancing and safe chunking.
- Rate limiting and priority dispatching.
- Process tree termination and cleanup.
- Access control middleware and command handlers.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
