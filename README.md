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

SparkGram adalah bridge Telegram untuk menjalankan dan mengontrol AI coding assistant (seperti OpenCode) langsung dari chat Telegram di HP maupun desktop ke komputer lokal atau server kamu.

---

## 🎯 Gambaran Kerja

```
[ Telegram Chat ] ──(Prompt / Voice / Photo / Files)──> [ SparkGram Bridge ]
                                                               │
                                                               ▼
[ HP / Desktop ]  <──(Streaming HTML / Git / Snapshots)─ [ Subprocess Engine ]
                                                               │
                                                               ▼
                                                       [ Local Workspace / Git / Ports ]
```

Dengan SparkGram, kamu bisa:
- Menjalankan prompt coding, debugging, dan review kode langsung dari Telegram.
- **⏰ Self-Hosted Cron Scheduler**: Menjadwalkan tugas berkala (`/schedule 0 9 * * * prompt`, `/jobs`, `/unschedule`) langsung berjalan di laptop/server tanpa cloud.
- **🧠 Persistent Memory**: Menyimpan memori fakta & konteks cross-session (`/memory`, auto-inject prompt) berbasis format markdown yang transparan.
- **Git Cockpit Interaktif**: Melihat status staged/unstaged, visual diff, 1-tap AI Conventional Commit, dan push remote dari HP.
- **Developer Recipe Hub & Macros**: Menjalankan resep otomasi instan (`/review`, `/testgen`, `/explain`, `/refactor`, `/doc`).
- **Inline File Explorer & Artifact Delivery**: Menjelajahi file proyek (`/files`, `/cat`), mengunduh arsip `.zip` bersih, dan mengunggah konfigurasi/kode dengan auto-backup `.bak`.
- **Live Web UI Preview (`/preview`, `/snap`)**: Memotret tampilan live frontend web di `localhost:3000`/`localhost:5173` dalam mode Mobile (390px) atau Desktop (1440p) via Playwright.
- **Local Port & Process Manager (`/ports`, `/killport`)**: Memantau port dev yang aktif di laptop dan mematikan dev server yang macet / zombie seketika.
- Memantau output streaming secara live tanpa membuat antrean pesan Telegram tersendat.
- Berpindah model AI (Spark, Groq, DeepSeek, Claude, dll.) hanya dengan 1 ketukan tombol.
- Mengirim screenshot error atau terminal untuk dianalisis bersama instruksi yang kamu berikan.
- Memantau status hardware laptop/PC (CPU, RAM, Disk, Suhu GPU, dan Baterai).

---

## 🚀 Panduan Instalasi & Menjalankan

### Persyaratan:
- Python 3.10 atau versi yang lebih baru
- CLI AI terpasang (misal: [OpenCode](https://github.com/opencode-ai/opencode))
- Token Telegram Bot dari [@BotFather](https://t.me/BotFather)

### 1. Clone & Instal Dependensi

```bash
git clone https://github.com/Reyn1551/SparkGram.git
cd SparkGram
pip install -e .
playwright install chromium
```

### 2. Konfigurasi Environment

Buat file `.env` di folder root (atau salin dari contoh):

```env
TELEGRAM_BOT_TOKEN="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
ALLOWED_USER_IDS="1925430810"
WORK_DIR="C:\Path\Ke\Project\Kamu"
MODEL="opencode/muse-spark-1.2-contributor-free"
GROQ_API_KEY="" # Opsional, jika menggunakan fitur transkripsi suara
```

> **Catatan Keamanan:** Selalu isi `ALLOWED_USER_IDS` dengan Telegram User ID kamu untuk mencegah akses tidak sah ke terminal komputer kamu. Dapatkan ID kamu via perintah `/id` ke bot.

### 3. Jalankan Bot

```bash
# Menggunakan modul Python
python -m sparkgram

# Atau jalankan script live bridge (dengan auto-restart watchdog)
python bot_bridge_live.py
```

---

## 📱 Fitur Unggulan

### 1. 📸 Live Web UI Snapshot (`/preview [port|url]`, `/snap`)
- Memotret live render web app frontend lokal (Vite, Next.js, FastAPI, Streamlit, HTML) menggunakan browser Playwright headless di PC kamu.
- **Responsive Viewport Switcher**: Beralih instan antara mode `📱 Mobile (390px iPhone)` dan `💻 Desktop (1440p)` via inline buttons.
- **Console Log Triage**: Memeriksa pesan error JavaScript (`console.error`, `console.warn`) dari browser untuk debugging instan.
- **Proteksi SSRF Ketat**: Hanya mengizinkan loopback lokal dan memblokir intranet/cloud metadata.
- **Lazy Auto-Kill**: Mematikan instance browser otomatis saat tidak digunakan untuk menghemat RAM komputer.

### 2. 🔌 Local Port & Process Killer (`/ports`, `/killport`)
- Memindai seluruh port TCP yang sedang aktif mendengarkan (LISTEN) di komputer kamu.
- Menampilkan nama proses, PID, penggunaan memori (MB), dan jenis layanan.
- **1-Tap Process Killer**: Mematikan proses server yang menyangkut (`EADDRINUSE`) secara bersih beserta seluruh anak prosesnya (*zero zombie*).
- **1-Tap Web Preview**: Langsung melompat memotret web preview dari port yang aktif.

### 3. 🌿 Interactive Git Cockpit (`/git`, `/diff`, `/commit`, `/push`)
- Panel visual status repositori (staged 🟢, unstaged 🟡, untracked ⚪).
- Diff viewer per-file di dalam `<blockquote expandable>` yang rapi di layar HP.
- **1-Tap AI Commit**: Otomatis menghasilkan pesan *Conventional Commit* semantik dari perubahan kode yang di-stage.
- Ekspor patch `.diff` standar langsung dikirim sebagai lampiran dokumen Telegram.

### 4. 🎛️ Developer Recipes & Macro Hub (`/macro`)
- Resep prompt siap pakai dengan injeksi konteks lokal dan optimasi *Prompt Caching*:
  - `/review` — Audit security, race conditions, memory leaks, dan error handling pada staged diff.
  - `/testgen <file>` — Otomatis membuat automated test suite pytest lengkap dengan mock & edge cases.
  - `/explain <file>` — Deep code tracing dan penjelasan dependensi modul.
  - `/refactor <file>` — Refactoring clean code & performa tinggi.
  - `/doc <file>` — Menulis dokumentasi teknis & docstring.

### 5. 📁 Inline File Explorer & Artifact Delivery (`/files`, `/cat`, `/download`)
- Menjelajahi folder proyek via Telegram Inline Buttons dengan sistem paginasi.
- Mengunduh file atau direktori sebagai `.zip` bersih (otomatis menyaring `.git`, `node_modules`, `.venv`, dan file `.env` sensitif).
- Mengunggah file dari Telegram ke komputer dengan proteksi *Chroot Jail* dan backup atomik `.bak` otomatis.

### 6. ⚡ Tampilan Chat yang Rapi (Mobile & Desktop)
- **Collapsible Block (`<blockquote expandable>`)**: Jejak pemikiran (*reasoning trace*), diff git yang panjang, dan log terminal otomatis terlipat rapi sehingga tidak memenuhi layar HP.
- **Syntax Highlighting**: Blok kode otomatis diformat sesuai bahasa pemrograman dengan tag `<pre><code class="language-xyz">`.
- **Indikator Selesai**: Setiap pesan yang selesai diproses memiliki badge status jelas (`✅ Selesai`) lengkap dengan durasi dan timestamp.

### 7. 🛡️ Kontrol Proses yang Aman & Zero-Zombie
- Menggunakan Win32 Job Object di Windows dan POSIX process group di Linux/macOS untuk memastikan seluruh subproses dan pohon proses anak benar-benar mati saat perintah `/cancel` atau tombol `[🛑 Batalkan Job]` ditekan.

---

## 🕹️ Daftar Perintah Telegram

| Kategori | Perintah | Fungsi |
|---|---|---|
| **NAV (Explorer & WorkDir)** | `/nav` | Explorer WORK_DIR + inline buttons (pengganti `/files`, `/tree`) |
| | `/nav pwd` | Lihat workdir aktif (pengganti `/pwd`, `/workdir` tanpa arg) |
| | `/nav ls [path]` | List folder (tanpa ubah workdir) |
| | `/nav cd <path>` | Ganti workdir — fuzzy `desktop/.../hyperspectral`, `~`, absolute |
| | `/nav cd ..` | Mundur ke parent (maju/mundur ala `cd ..`) |
| | `/nav cd -` | Kembali ke workdir sebelumnya (history) |
| | `/nav cat <file>` | Preview file (pengganti `/cat`) |
| | `/nav dl <path>` | Download file/zip (pengganti `/download`) |
| **SESSION** | `/session` | List sesi workdir ini (pengganti `/sessions`) |
| | `/session switch 1` | Ganti sesi aktif (pengganti `/switch`) |
| | `/session new` | Session baru (pengganti `/new`) |
| | `/session rename <judul>` | Rename sesi (pengganti `/rename`) |
| | `/session delete <id>` | Hapus sesi (pengganti `/delete`) |
| | `/session export` | Export markdown (pengganti `/export`) |
| **GIT** | `/git` | Cockpit status git interaktif |
| | `/git diff [staged]` | Diff (pengganti `/diff`) |
| | `/git commit [pesan]` | Commit (pengganti `/commit`) |
| | `/git push [remote]` | Push (pengganti `/push`) |
| **RECIPE** | `/recipe` | Hub interaktif (pengganti `/macro`) |
| | `/recipe review` | Review diff staged (pengganti `/review`) |
| | `/recipe testgen <file>` | Generate test (pengganti `/testgen`) |
| | `/recipe explain <file>` | Explain (pengganti `/explain`) |
| | `/recipe refactor <file>` | Refactor (pengganti `/refactor`) |
| **SYS** | `/sys health` | Telemetri hardware (pengganti `/health`, `/sysinfo`) |
| | `/sys logs [n]` | Tail log (pengganti `/logs`) |
| | `/sys ports` | List ports dev (pengganti `/ports`) |
| | `/sys killport 3000` | Kill port (pengganti `/killport`) |
| | `/sys preview [port\|url]` | Snapshot web (pengganti `/preview`, `/snap`) |
| **JOBS** | `/jobs` | List cron scheduler |
| | `/jobs add <cron> <prompt>` | Buat jadwal (pengganti `/schedule`) |
| | `/jobs rm <id>` | Hapus jadwal (pengganti `/unschedule`) |
| | `/jobs run <id>` | Jalankan manual |
| **AI & Memory** | `/model` | Ganti model AI 1-tap |
| | `/memory [query]` | Search persistent memory |
| | `/id` `/cancel` `/help` | Utility — ID, cancel job, bantuan |

---

## 📁 Struktur Kode (`sparkgram/`)

```
sparkgram/
├── bot/                 # Handler Telegram (perintah, callback, media, teks)
├── core/                # Pengelolaan state sesi dan model AI
├── engine/              # Eksekusi subproses, pemantau pohon proses, stream reader
├── scheduler/           # Self-hosted Cron Scheduler (5-field cron parsing & runner)
├── memory/              # Persistent memory manager (markdown inspectable)
├── ratelimit/           # Pengatur batas laju permintaan dan pencegah error 429
├── formatters/          # Konversi Markdown ke Telegram HTML dan penyeimbang tag
├── supervisor/          # Watchdog file untuk auto-reload saat kode diubah
├── adapters/            # Adapter OpenCode CLI dan Groq Whisper
└── utils/               # Pemantau telemetri sistem dan masker data sensitif
```

---

## 🧪 Pengujian Otomatis

Semua modul inti diuji menggunakan `pytest`:

```bash
pytest -v tests/
```

Test suite memvalidasi:
- Penyeimbang tag HTML dan pemotongan paragraf aman.
- Rate limiter dan antrean prioritas.
- Terminasi pohon proses (*process tree manager*).
- Middleware whitelist ID dan handler perintah bot.

---

## 📄 Lisensi

Proyek ini dilisensikan di bawah [MIT License](LICENSE).
