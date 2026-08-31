# SparkGram PnP Installer — Windows (PowerShell)
param([string]$Repo="https://github.com/Reyn1551/SparkGram.git", [string]$Dir="$env:USERPROFILE\telegram-opencode-bridge")
Write-Host "=== SparkGram PnP Install (Windows) ===" -ForegroundColor Green
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Write-Host "git belum ada, install dari https://git-scm.com" -ForegroundColor Red; exit 1 }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-Host "python belum ada" -ForegroundColor Red; exit 1 }
if (Test-Path $Dir) { Write-Host "Dir $Dir sudah ada, update..." -ForegroundColor Yellow; Set-Location $Dir; git pull; } else { git clone $Repo $Dir; Set-Location $Dir }
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Write-Host ".env dibuat dari .env.example — isi TELEGRAM_BOT_TOKEN!" -ForegroundColor Yellow; notepad ".env" }
pip install -r requirements.txt
Write-Host "=== Test opencode ===" -ForegroundColor Cyan
opencode --version 2>&1 | Write-Host
Write-Host "=== Start bridge ===" -ForegroundColor Green
Write-Host "Jalankan: python bot_bridge_live.py  atau  .\scripts\run_bridge_loop.ps1 (auto-restart)"
Write-Host "Cek di Telegram: /start  /sessions  /workdir" -ForegroundColor Green
Write-Host "Logs: $env:TEMP\telegram-bridge\bridge.log" -ForegroundColor Gray
# auto-start loop
$ans = Read-Host "Jalankan bridge sekarang? (y/n)"
if ($ans -eq "y") { powershell -ExecutionPolicy Bypass -File "scripts\run_bridge_loop.ps1" }
