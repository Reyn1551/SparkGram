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

SparkGram is a Telegram bridge that lets you run a local AI coding assistant like OpenCode directly from a chat on your phone or desktop.

---

## How it works

```
[ Telegram Chat ] ──(Prompt / Voice / Photo / Files)──> [ SparkGram Bridge ]
                                                               │
                                                               ▼
[ Mobile / Desktop ] <──(Streaming HTML / Git / Snaps)─── [ Subprocess Engine ]
                                                               │
                                                               ▼
                                                       [ Local Workspace / Git / Ports ]
```

From Telegram you can send coding prompts, debug requests, and reviews without opening the laptop. Highlights:

- Run prompts with live streaming output that does not block the message queue.
- Schedule recurring tasks on your own machine (`/schedule 0 9 * * * prompt`, `/jobs`, `/unschedule`) with no cloud service.
- Keep cross-session context as plain markdown you can read and edit (`/memory`, auto-injected into prompts).
- Check staged, unstaged, and untracked changes from your phone, view diffs that fold nicely on small screens, create a Conventional Commit with one tap, and push.
- Run ready-made recipes like `/review`, `/testgen`, `/explain`, `/refactor`, and `/doc` with local repo context already injected.
- Browse the workspace with inline buttons (`/nav`, `/nav ls`, `/nav cat`), download clean zips that filter out `.git` and `.env`, and upload files with an automatic `.bak` backup.
- Capture a live frontend at `localhost:3000` or `localhost:5173` via Playwright and switch between mobile 390px and desktop 1440p (`/preview`, `/snap`), including browser console logs.
- Scan listening ports on the host and kill a hung dev server in one tap (`/ports`, `/killport`).
- Switch models (Spark, Groq, DeepSeek, and others) with buttons, send screenshots for analysis, and check CPU, RAM, disk, GPU temperature, and battery.

---

## Quick setup

### Prerequisites

- Python 3.10 or higher
- An AI coding CLI such as [OpenCode](https://github.com/opencode-ai/opencode)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

### 1. Clone and install

```bash
git clone https://github.com/Reyn1551/SparkGram.git
cd SparkGram
pip install -e .
playwright install chromium
```

### 2. Configure environment

Create a `.env` file in the root:

```env
TELEGRAM_BOT_TOKEN="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
ALLOWED_USER_IDS="1925430810"
WORK_DIR="C:\Path\To\Your\Project"
MODEL="opencode/muse-spark-1.2-contributor-free"
GROQ_API_KEY="" # optional, for voice transcription
```

Restrict `ALLOWED_USER_IDS` to your own Telegram ID so only you can run commands on the machine. Send `/id` to the bot to find your ID.

### 3. Run the bot

```bash
# as a Python module
python -m sparkgram

# or with the auto-reload watchdog
python bot_bridge_live.py
```

---

## Features

### Live web snapshot (`/preview [port|url]`, `/snap`)

Captures a local frontend (Vite, Next.js, FastAPI, Streamlit) through a headless Playwright instance on your machine. Switch between mobile and desktop with inline buttons, capture `console.error` and `console.warn` for debugging, and only loopback addresses are allowed to block access to private networks. The browser shuts down automatically when idle to save RAM.

### Port and process (`/ports`, `/killport`)

Scans TCP LISTEN ports and shows process name, PID, and memory use. If a port collides with `EADDRINUSE`, you can kill the process and its children cleanly in one tap with no zombies left.

### Git cockpit (`/git`, `/diff`, `/commit`, `/push`)

Status board for staged, unstaged, and untracked files. Diffs are rendered per file inside `blockquote expandable` so they stay readable on a phone. The commit button summarizes staged changes into a semantic Conventional Commit message, and you can export a standard `.diff` patch as a document.

### Recipe hub (`/recipe`)

Ready-to-run prompts with local repo context:

- `/review` checks staged diffs for security, race conditions, and error handling
- `/testgen <file>` builds a pytest suite with mocks and edge cases
- `/explain <file>` traces code and dependencies
- `/refactor <file>` cleans up code and improves performance
- `/doc <file>` writes markdown docs and docstrings

### File explorer (`/nav`, `/nav ls`, `/nav cat`, `/nav dl`)

Browse directories with paginated inline keyboards. Download single files or zips that filter out `.git`, `node_modules`, `.venv`, and `.env`. Uploads from Telegram are confined to WORK_DIR and the old file is saved as `.bak`.

### Chat typography

Long reasoning traces, diffs, and terminal logs fold into `blockquote expandable` so they do not fill the phone screen. Code blocks get proper language highlighting with `<pre><code class="language-...">`, and finished replies show duration and timestamp.

### Process management

On Windows the bridge uses Job Objects and on Linux or macOS it uses process groups, so when you press `/cancel` or the cancel button, the whole subprocess tree is terminated cleanly.

---

## Command reference

| Category | Command | Description |
|---|---|---|
| **NAV** | `/nav` | Browse WORK_DIR with inline buttons |
| | `/nav pwd` | Show active workdir |
| | `/nav ls [path]` | List folder without changing workdir |
| | `/nav cd <path>` | Change workdir, supports `desktop/...`, `~`, absolute, fuzzy |
| | `/nav cd ..` | Go to parent |
| | `/nav cd -` | Back to previous workdir |
| | `/nav cat <file>` | Preview file |
| | `/nav dl <path>` | Download file or zip |
| **SESSION** | `/session` | List sessions in this workdir |
| | `/session switch 1` | Switch active session |
| | `/session new` | Create new session |
| | `/session rename <title>` | Rename session |
| | `/session delete <id>` | Delete session |
| | `/session export` | Export markdown |
| **GIT** | `/git` | Interactive status panel |
| | `/git diff [staged]` | Show diff |
| | `/git commit [msg]` | Commit |
| | `/git push [remote]` | Push |
| **RECIPE** | `/recipe` | Open recipe hub |
| | `/recipe review` | Review staged diff |
| | `/recipe testgen <file>` | Generate tests |
| | `/recipe explain <file>` | Explain code |
| | `/recipe refactor <file>` | Refactor |
| **SYS** | `/sys health` | Check CPU, RAM, disk, GPU, battery |
| | `/sys logs [n]` | Tail logs |
| | `/sys ports` | List dev ports |
| | `/sys killport 3000` | Kill process on port |
| | `/sys preview [port|url]` | Web snapshot |
| **JOBS** | `/jobs` | List cron scheduler |
| | `/jobs add 0 9 * * * prompt` | Create schedule |
| | `/jobs rm <id>` | Remove schedule |
| | `/jobs run <id>` | Run now |
| **AI & Memory** | `/model` | Switch model with buttons |
| | `/memory [query]` | Search memory |
| | `/id` `/cancel` `/help` | Utilities |

---

## Repository structure (`sparkgram/`)

```
sparkgram/
├── bot/                 # Telegram handlers (commands, callbacks, media, messages)
├── core/                # Session state and models
├── engine/              # Subprocess, process tree, stream reader
├── scheduler/           # Self-hosted cron scheduler
├── memory/              # Markdown memory store
├── ratelimit/           # Rate limiting and 429 guard
├── formatters/          # Markdown to Telegram HTML
├── supervisor/          # File watchdog auto-reload
├── adapters/            # OpenCode and Groq adapters
└── utils/               # Health monitor and log masker
```

---

## Automated testing

Core modules are tested with `pytest`:

```bash
pytest -v tests/
```

Coverage includes HTML tag balancing, rate limiting, process tree termination, and access middleware.

---

## License

MIT. See [LICENSE](LICENSE).
