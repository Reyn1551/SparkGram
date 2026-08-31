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

SparkGram adalah bridge Telegram untuk menjalankan dan mengontrol AI coding assistant (seperti OpenCode) langsung dari chat Telegram di HP maupun desktop ke komputer lokal atau server kamu.

---

## 🎯 Gambaran Kerja

```
[ Telegram Chat ] ──(Prompt / Voice / Photo)──> [ SparkGram Bridge ]
                                                        │
                                                        ▼
[ HP / Desktop ]  <──(Streaming HTML / Cards)─── [ Subprocess Engine ]
                                                        │
                                                        ▼
                                                [ Local Workspace / Git ]
```

Dengan SparkGram, kamu bisa:
- Menjalankan prompt coding, debugging, dan review kode langsung dari Telegram.
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

## 📱 Fitur Utama

### 1. Tampilan Chat yang Rapi (Mobile & Desktop)
- **Collapsible Block (`<blockquote expandable>`)**: Jejak pemikiran (*reasoning trace*), diff git yang panjang, dan log terminal otomatis terlipat rapi sehingga tidak memenuhi layar HP.
- **Syntax Highlighting**: Blok kode otomatis diformat sesuai bahasa pemrograman dengan tag `<pre><code class="language-xyz">`.
- **Indikator Selesai**: Setiap pesan yang selesai diproses memiliki badge status jelas (`✅ Selesai`) lengkap dengan durasi dan timestamp.

### 2. Kontrol Proses yang Aman (Zero Zombie)
- Menggunakan Win32 Job Object di Windows dan POSIX process group di Linux/macOS untuk memastikan seluruh subproses dan pohon proses anak benar-benar mati saat perintah `/cancel` atau tombol `[🛑 Batalkan Job]` ditekan.

### 3. Perlindungan Rate Limit Telegram
- Dilengkapi sistem *2-Tier Token Bucket* (Global 28 req/s dan Per-chat 1.0–1.2 req/s) serta penyeimbang tag HTML (*HTML Tag Balancer*) agar bot tidak terkena penalti *Too Many Requests (HTTP 429)* atau *Bad Request (HTTP 400)*.

### 4. Telemetri Hardware Host (`/health`)
- Memantau penggunaan CPU, RAM, Disk C:, Suhu GPU NVIDIA GTX 1650, dan status Baterai/Charger laptop kamu dari jarak jauh.

---

## 🕹️ Daftar Perintah Telegram

| Perintah | Fungsi |
|---|---|
| `/start`, `/help` | Menampilkan panduan penggunaan dan status bot |
| `/model` | Membuka menu interaktif untuk mengganti model AI (1-tap) |
| `/sessions` | Melihat dan berpindah ke riwayat sesi percakapan sebelumnya |
| `/new` | Memulai sesi baru dengan konteks bersih |
| `/workdir [path]` | Melihat atau mengganti folder direktori proyek yang sedang dikerjakan |
| `/status` | Melihat apakah bot sedang sibuk memproses atau dalam status idle |
| `/health` | Memeriksa telemetri hardware laptop/server (CPU, RAM, Suhu, Baterai) |
| `/logs [n]` | Mengambil baris log terbaru dari background bridge |
| `/cancel` | Menghentikan paksa proses coding yang sedang berjalan |
| `/id` | Menampilkan Telegram ID kamu dan ID chat saat ini |

---

## 📁 Struktur Kode (`sparkgram/`)

```
sparkgram/
├── bot/                 # Handler Telegram (perintah, callback, media, teks)
├── core/                # Pengelolaan state sesi dan model AI
├── engine/              # Eksekusi subproses, pemantau pohon proses, stream reader
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
