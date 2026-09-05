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

SparkGram adalah bridge Telegram untuk menjalankan AI coding assistant seperti OpenCode langsung dari chat HP atau desktop ke komputer lokal atau server kamu.

---

## Gambaran kerja

```
[ Telegram Chat ] ──(Prompt / Voice / Photo / Files)──> [ SparkGram Bridge ]
                                                               │
                                                               ▼
[ HP / Desktop ]  <──(Streaming HTML / Git / Snapshots)─ [ Subprocess Engine ]
                                                               │
                                                               ▼
                                                       [ Local Workspace / Git / Ports ]
```

Dengan SparkGram kamu bisa menjalankan prompt coding, debug, dan review langsung dari Telegram, tanpa membuka laptop. Fitur intinya:

- Menjalankan prompt coding dan review langsung dari Telegram, dengan streaming output tanpa membuat antrean pesan macet.
- Menjadwalkan tugas berkala di laptop atau server sendiri (`/schedule 0 9 * * * prompt`, `/jobs`, `/unschedule`) tanpa layanan cloud.
- Menyimpan konteks antar sesi sebagai markdown yang bisa kamu baca dan edit (`/memory`, auto-inject ke prompt).
- Melihat status git staged, unstaged, dan untracked dari HP, melihat diff yang rapi di layar kecil, membuat commit Conventional Commit dengan satu ketuk, lalu push.
- Menjalankan resep siap pakai seperti `/review`, `/testgen`, `/explain`, `/refactor`, dan `/doc` dengan injeksi konteks lokal.
- Menjelajahi file proyek lewat tombol inline (`/nav`, `/nav ls`, `/nav cat`), mengunduh folder sebagai zip yang sudah menyaring `.git` dan `.env`, serta mengunggah file dengan backup `.bak` otomatis.
- Memotret tampilan frontend lokal di `localhost:3000` atau `localhost:5173` lewat Playwright, bisa pilih mode mobile 390px atau desktop 1440p (`/preview`, `/snap`), termasuk log console browser.
- Melihat port yang sedang listen di laptop dan mematikan dev server yang nyangkut dengan satu ketuk (`/ports`, `/killport`).
- Ganti model AI (Spark, Groq, DeepSeek, dan lain-lain) lewat tombol, kirim screenshot error untuk dianalisis, serta cek CPU, RAM, disk, suhu GPU, dan baterai.

---

## Instalasi dan menjalankan

### Persyaratan

- Python 3.10 atau lebih baru
- CLI AI seperti [OpenCode](https://github.com/opencode-ai/opencode)
- Token bot Telegram dari [@BotFather](https://t.me/BotFather)

### 1. Clone dan instal dependensi

```bash
git clone https://github.com/Reyn1551/SparkGram.git
cd SparkGram
pip install -e .
playwright install chromium
```

### 2. Konfigurasi environment

Buat file `.env` di root atau salin dari contoh:

```env
TELEGRAM_BOT_TOKEN="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
ALLOWED_USER_IDS="1925430810"
WORK_DIR="C:\Path\Ke\Project\Kamu"
MODEL="opencode/muse-spark-1.2-contributor-free"
GROQ_API_KEY="" # opsional, untuk transkripsi suara
```

Isi `ALLOWED_USER_IDS` dengan ID Telegram kamu agar hanya kamu yang bisa menjalankan perintah di terminal. Kirim `/id` ke bot untuk melihat ID.

### 3. Jalankan bot

```bash
# sebagai modul Python
python -m sparkgram

# atau dengan watchdog auto-restart saat kode berubah
python bot_bridge_live.py
```

---

## Fitur

### Live web snapshot (`/preview [port|url]`, `/snap`)

Memotret render frontend lokal (Vite, Next.js, FastAPI, Streamlit) lewat Playwright headless di komputermu. Kamu bisa beralih antara mobile dan desktop lewat tombol inline, melihat log `console.error` dan `console.warn` untuk debug, dan browser hanya mengizinkan alamat loopback untuk mencegah akses ke jaringan privat. Browser dimatikan otomatis saat tidak dipakai untuk menghemat RAM.

### Port dan proses (`/ports`, `/killport`)

Memindai port TCP yang sedang listen, menampilkan nama proses, PID, dan pemakaian memori. Jika port bentrok `EADDRINUSE`, kamu bisa mematikan proses beserta turunannya dengan satu ketuk tanpa menyisakan zombie.

### Git cockpit (`/git`, `/diff`, `/commit`, `/push`)

Panel status menampilkan staged, unstaged, dan untracked. Diff ditampilkan per file di dalam `blockquote expandable` agar nyaman di HP. Tombol commit akan membuat pesan Conventional Commit dari perubahan yang sudah di-stage, dan kamu bisa ekspor patch `.diff` sebagai dokumen.

### Resep developer (`/recipe`)

Kumpulan prompt siap pakai yang sudah diisi konteks lokal:

- `/review` untuk audit security, race condition, dan error handling pada staged diff
- `/testgen <file>` untuk membuat rangkaian test pytest dengan mock dan edge case
- `/explain <file>` untuk tracing kode dan dependensi
- `/refactor <file>` untuk refactoring yang lebih bersih
- `/doc <file>` untuk menulis docstring dan dokumentasi

### File explorer (`/nav`, `/nav ls`, `/nav cat`, `/nav dl`)

Jelajahi folder lewat tombol inline dengan paginasi. Unduhan file atau folder berupa zip yang otomatis menyaring `.git`, `node_modules`, `.venv`, dan `.env`. Upload file dari Telegram dibatasi ke dalam WORK_DIR dan file lama di-backup sebagai `.bak`.

### Tampilan chat

Jejak reasoning, diff panjang, dan log terminal otomatis terlipat dengan `blockquote expandable` sehingga tidak memenuhi layar HP. Blok kode diberi highlight sesuai bahasa dengan `<pre><code class="language-...">`, dan setiap balasan yang selesai menampilkan durasi dan waktu.

### Kontrol proses

Di Windows memakai Job Object dan di Linux atau macOS memakai process group, jadi saat kamu menekan `/cancel` atau tombol Batalkan, semua subproses benar-benar dimatikan tanpa sisa.

---

## Daftar perintah

| Kategori | Perintah | Fungsi |
|---|---|---|
| **NAV** | `/nav` | Explorer WORK_DIR dengan tombol inline |
| | `/nav pwd` | Lihat workdir aktif |
| | `/nav ls [path]` | List folder tanpa pindah workdir |
| | `/nav cd <path>` | Ganti workdir, mendukung `desktop/.../hyperspectral`, `~`, absolute, dan fuzzy |
| | `/nav cd ..` | Mundur ke parent |
| | `/nav cd -` | Kembali ke workdir sebelumnya |
| | `/nav cat <file>` | Preview file |
| | `/nav dl <path>` | Download file atau zip |
| **SESSION** | `/session` | List sesi di workdir ini |
| | `/session switch 1` | Ganti sesi aktif |
| | `/session new` | Buat sesi baru |
| | `/session rename <judul>` | Rename sesi |
| | `/session delete <id>` | Hapus sesi |
| | `/session export` | Ekspor markdown |
| **GIT** | `/git` | Panel status interaktif |
| | `/git diff [staged]` | Lihat diff |
| | `/git commit [pesan]` | Commit |
| | `/git push [remote]` | Push |
| **RECIPE** | `/recipe` | Buka hub resep |
| | `/recipe review` | Review staged diff |
| | `/recipe testgen <file>` | Buat test |
| | `/recipe explain <file>` | Jelaskan kode |
| | `/recipe refactor <file>` | Refactor |
| **SYS** | `/sys health` | Cek CPU, RAM, disk, GPU, baterai |
| | `/sys logs [n]` | Tail log |
| | `/sys ports` | List port dev |
| | `/sys killport 3000` | Matikan proses di port |
| | `/sys preview [port|url]` | Snapshot web |
| **JOBS** | `/jobs` | List scheduler cron |
| | `/jobs add 0 9 * * * prompt` | Buat jadwal |
| | `/jobs rm <id>` | Hapus jadwal |
| | `/jobs run <id>` | Jalankan manual |
| **AI & Memory** | `/model` | Ganti model dengan tombol |
| | `/memory [query]` | Cari memory |
| | `/id` `/cancel` `/help` | Alat bantu |

---

## Struktur kode (`sparkgram/`)

```
sparkgram/
├── bot/                 # Handler Telegram (perintah, callback, media, teks)
├── core/                # State sesi dan model
├── engine/              # Subprocess, process tree, stream reader
├── scheduler/           # Cron scheduler self-hosted
├── memory/              # Penyimpanan memory markdown
├── ratelimit/           # Rate limiter dan pencegah 429
├── formatters/          # Markdown ke HTML Telegram
├── supervisor/          # Watchdog auto-reload
├── adapters/            # Adapter OpenCode dan Groq
└── utils/               # Health monitor dan log masker
```

---

## Pengujian

Semua modul inti diuji dengan `pytest`:

```bash
pytest -v tests/
```

Cakupan test meliputi penyeimbang tag HTML, rate limiter, terminasi process tree, dan middleware whitelist.

---

## Lisensi

MIT. Lihat [LICENSE](LICENSE).
