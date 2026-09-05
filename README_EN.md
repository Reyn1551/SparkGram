# SparkGram

<p align="center">
  <a href="README.md">🇮🇩 Bahasa Indonesia</a> • <a href="README_EN.md">🇬🇧 English</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Telegram_Bot_API-7.3+-2CA5E0?style=flat-square&logo=telegram&logoColor=white" />
  <img src="https://img.shields.io/badge/Tests-66_Passed-44cc11?style=flat-square&logo=pytest&logoColor=white" />
  <img src="https://img.shields.io/badge/Platform-Windows_|_Linux_|_macOS-24292e?style=flat-square" />
  <img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" />
</p>

SparkGram is a lightweight Telegram bridge that lets you run and control your local AI coding assistant (such as OpenCode) directly from Telegram chat on your mobile phone or desktop.

---

## 🎯 How It Works

```
[ Telegram Chat ] ──(Prompt / Voice / Photo / Files)──> [ SparkGram Bridge ]
                                                               │
                                                               ▼
[ Mobile / Desktop ] <──(Streaming HTML / Git / Snaps)─── [ Subprocess Engine ]
                                                               │
                                                               ▼
                                                       [ Local Workspace / Git / Ports ]
```

With SparkGram, you can:
- Send coding prompts, debug requests, and code reviews straight from Telegram.
- **⏰ Self-Hosted Cron Scheduler**: Schedule automated recurring tasks (`/schedule 0 9 * * * prompt`, `/jobs`, `/unschedule`) running locally with zero cloud dependencies.
- **🧠 Persistent Memory**: Store cross-session facts and context (`/memory`, auto prompt context injection) backed by human-inspectable markdown.
- **Interactive Git Cockpit**: Inspect staged/unstaged changes, visual diffs, 1-tap AI Conventional Commits, and push to remote directly from your phone.
- **Developer Recipe Hub & Macros**: Execute automated recipes instantly (`/review`, `/testgen`, `/explain`, `/refactor`, `/doc`).
- **Inline File Explorer & Artifact Delivery**: Browse workspace folders (`/files`), view code previews (`/cat`), download clean `.zip` archives, and upload configuration files with automated `.bak` backups.
- **Live Web UI Preview (`/preview`, `/snap`)**: Capture live frontend rendering (`localhost:3000`, `localhost:5173`) in Mobile (390px) or Desktop (1440p) views via Playwright.
- **Local Port & Process Manager (`/ports`, `/killport`)**: Scan active host listening ports and kill hung dev servers with 1 tap.
- Watch live streaming output without blocking the chat message queue.
- Switch AI models (Spark, Groq, DeepSeek, Claude, dll.) with 1-tap inline buttons.
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
playwright install chromium
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

### 1. 📸 Live Web UI Snapshot (`/preview [port|url]`, `/snap`)
- Captures live rendered frontend web apps (Vite, Next.js, FastAPI, Streamlit, HTML) using a headless Playwright Chromium instance.
- **Responsive Viewport Switcher**: Toggle instantly between `📱 Mobile (390px iPhone)` and `💻 Desktop (1440p)` via inline buttons.
- **Console Log Triage**: Captures JavaScript errors (`console.error`, `console.warn`) for fast debugging.
- **Strict SSRF Defense**: Only loopback local addresses are permitted; blocks cloud metadata and private subnets.
- **Lazy Auto-Kill**: Shuts down browser instance after 120s of inactivity to conserve host RAM.

### 2. 🔌 Local Port & Process Killer (`/ports`, `/killport`)
- Scans all active TCP LISTEN ports on your host PC.
- Displays process name, PID, memory usage (MB), and web service type.
- **1-Tap Process Killer**: Cleanly terminates hung dev servers (`EADDRINUSE`) along with entire process trees (*zero zombies*).
- **1-Tap Web Preview**: Jump straight to web snapshot from active port cards.

### 3. 🌿 Interactive Git Cockpit (`/git`, `/diff`, `/commit`, `/push`)
- Visual repository status board (staged 🟢, unstaged 🟡, untracked ⚪).
- Per-file diff viewer rendered inside mobile-friendly `<blockquote expandable>`.
- **1-Tap AI Commit**: Automatically summarizes staged code modifications into semantic *Conventional Commit* messages.
- Standard `.diff` patch export sent directly as a Telegram document.

### 4. 🎛️ Developer Recipes & Macro Hub (`/macro`)
- Ready-to-run prompt recipes with local repo context injection and *Prompt Caching* optimization:
  - `/review` — Scans staged diff for security vulnerabilities, race conditions, memory leaks, and error handling.
  - `/testgen <file>` — Automatically creates a comprehensive pytest unit test suite.
  - `/explain <file>` — Deep code tracing and module dependency breakdown.
  - `/refactor <file>` — Clean code and performance refactoring.
  - `/doc <file>` — Generates technical markdown documentation and docstrings.

### 5. 📁 Inline File Explorer & Artifact Delivery (`/files`, `/cat`, `/download`)
- Browse project directories via paginated Telegram inline keyboards.
- Download single files or clean `.zip` archives (automatically filters `.git`, `node_modules`, `.venv`, and sensitive `.env` files).
- Upload files from Telegram to PC with *Chroot Jail* boundary protection and automatic atomic `.bak` backups.

### 6. ⚡ Clean Chat Typography (Mobile & Desktop)
- **Collapsible Cards (`<blockquote expandable>`)**: Long thinking traces, git diffs, and terminal outputs fold into neat accordions to prevent mobile screen clutter.
- **Syntax Highlighting**: Code blocks are automatically formatted with proper language tags (`<pre><code class="language-xyz">`).
- **Clear Status Badges**: Finished messages clearly indicate completion (`✅ Selesai (Completed)`) along with execution time and timestamps.

### 7. 🛡️ Safe Process Management (Zero Zombies)
- Uses Win32 Job Objects on Windows and POSIX process groups on Linux/macOS to ensure child process trees are cleanly terminated whenever `/cancel` or the `[🛑 Batalkan Job]` button is triggered.

---

## 🕹️ Telegram Command Reference

| Category | Command | Description |
|---|---|---|
| **Web & Ports** | `/preview [port\|url]` | Capture live web snapshot on localhost (Mobile / Desktop) |
| | `/ports` | Interactive active TCP ports panel with 1-tap kill & preview |
| | `/killport [port]` | Kill the process tree occupying a specific port |
| **Git Cockpit** | `/git` | Interactive Git cockpit (staged, unstaged, branch, 1-tap push) |
| | `/diff [staged]` | Formatted visual diff summary of modified code |
| | `/commit [message]` | Commit staged files to Git (with 1-tap AI generator) |
| | `/push [remote]` | Push active branch to remote Git repository |
| **Recipes** | `/macro` | Open interactive Developer Recipe Hub |
| | `/review` | Review logic & security on staged Git diff |
| | `/testgen [file]` | Automatically generate pytest unit test suite |
| | `/explain [file]` | Deep code tracing & module architecture explanation |
| | `/refactor [file]` | Clean code refactoring & performance optimization |
| **Files** | `/files [path]`, `/tree` | Browse project directories via inline keyboard |
| | `/cat [file]` | Inspect preview of code or text files |
| | `/download [file\|dir]` | Download file or sanitized .zip archive to Telegram |
| **Cron & Memory** | `/schedule [cron] [prompt]` | Schedule automated tasks (5-field cron or @hourly/@daily) |
| | `/jobs` | View & manage scheduled cron jobs (pause, resume, run now) |
| | `/unschedule [id]` | Delete a scheduled cron task |
| | `/memory [query]` | View & search cross-session persistent facts and context |
| **Sessions & AI** | `/model` | Open 1-tap interactive AI model switcher |
| | `/sessions` | View and switch between active & previous sessions |
| | `/new` | Start a fresh session with clean context |
| | `/workdir [path]` | View or switch active project working directory |
| | `/health` | Inspect remote host telemetry (CPU, RAM, GPU temp, battery) |
| | `/status` | Check bridge queue and active runtime status |
| | `/logs [n]` | Fetch recent bridge execution logs |
| | `/cancel` | Forcefully terminate currently running coding job |
| | `/id` | Display your Telegram User ID and Chat ID |

---

## 📁 Repository Structure (`sparkgram/`)

```
sparkgram/
├── bot/                 # Telegram handlers (commands, callbacks, media, messages)
├── core/                # Session state persistence and model registries
├── engine/              # Subprocess execution, process tree management, stream reader
├── scheduler/           # Self-hosted Cron Scheduler (5-field cron parsing & runner)
├── memory/              # Persistent memory manager (markdown inspectable)
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
