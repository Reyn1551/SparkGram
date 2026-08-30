# Install Task Scheduler untuk auto-start + auto-restart
# Harus Run as Administrator untuk /RL HIGHEST — tapi fallback ke user level jika tidak admin
param(
    [switch]$Uninstall
)

$TaskName = "TelegramOpencodeBridge"
$BridgeDir = "C:\Users\Reynboo\telegram-opencode-bridge"
$Runner = Join-Path $BridgeDir "scripts\run_bridge_loop.ps1"
$LogDir = Join-Path $env:TEMP "telegram-bridge"

if ($Uninstall) {
    Write-Host "Uninstall task $TaskName..." -ForegroundColor Yellow
    schtasks /Delete /TN $TaskName /F 2>&1 | Write-Host
    # Cleanup autostart di Startup folder + Registry Run
    $startupLink = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\TelegramBridge.lnk"
    if (Test-Path $startupLink) { Remove-Item $startupLink -Force; Write-Host "Removed startup link" }
    try { Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name $TaskName -ErrorAction SilentlyContinue; Write-Host "Removed Registry Run" } catch {}
    # Hentikan runner yang jalan
    try { if (Test-Path (Join-Path $LogDir "runner.lock")) { Remove-Item (Join-Path $LogDir "runner.lock") -Force -ErrorAction SilentlyContinue } } catch {}
    Write-Host "Done." -ForegroundColor Green
    exit 0
}

# Validasi
if (-not (Test-Path $Runner)) { Write-Error "Runner tidak ditemukan: $Runner"; exit 1 }

# 0) Pre-clean: matikan proses stale agar tidak Conflict saat install ulang
Write-Host "=== Pre-clean stale bridge (cegah Conflict 409) ===" -ForegroundColor Cyan
try {
    $stale = Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*bot_bridge*" }
    # Hitung jumlah, jika >1 maka ada duplikat
    $cnt = ($stale | Measure-Object).Count
    Write-Host "Ditemukan $cnt proses bot_bridge* (akan sisakan runner saja)" -ForegroundColor Gray
} catch { Write-Host "Skip stale check: $($_.Exception.Message)" -ForegroundColor Yellow }

# 1) Buat Task Scheduler (utama — paling reliable, butuh Admin; fallback otomatis jika Access Denied)
Write-Host "`n=== Membuat Task Scheduler: $TaskName ===" -ForegroundColor Cyan
if (-not (Test-Path $Runner)) { Write-Error "Runner tidak ditemukan: $Runner"; exit 1 }

$psExe = (Get-Command powershell -ErrorAction SilentlyContinue).Source
if (-not $psExe) { $psExe = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" }
$actionArg = "-ExecutionPolicy Bypass -WindowStyle Hidden -NoProfile -File `"$Runner`""
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$taskCreated = $false
if ($isAdmin) {
    try { schtasks /Delete /TN $TaskName /F 2>$null | Out-Null } catch {}
    Write-Host "Mencoba buat task (HIGHEST, admin)..." -ForegroundColor Gray
    $out = schtasks /Create /TN $TaskName /TR "$psExe $actionArg" /SC ONLOGON /RL HIGHEST /F 2>&1 | Out-String
    Write-Host $out
    if ($LASTEXITCODE -eq 0 -and $out -notlike "*ERROR*") {
        Write-Host "Task dibuat (HIGHEST) OK" -ForegroundColor Green
        $taskCreated = $true
    } else {
        Write-Host "Gagal HIGHEST: $out" -ForegroundColor Yellow
        Write-Host "Fallback ke LIMITED..." -ForegroundColor Yellow
        $out2 = schtasks /Create /TN $TaskName /TR "$psExe $actionArg" /SC ONLOGON /F 2>&1 | Out-String
        Write-Host $out2
        if ($LASTEXITCODE -eq 0 -and $out2 -notlike "*ERROR*") {
            Write-Host "Task dibuat (LIMITED) OK" -ForegroundColor Green
            $taskCreated = $true
        }
    }
    # Tweak settings jika task berhasil
    if ($taskCreated) {
        try {
            $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
            $settings = $task.Settings
            $settings.RestartCount = 999
            $settings.RestartInterval = "PT1M"
            $settings.AllowDemandStart = $true
            $settings.StartWhenAvailable = $true
            $settings.DontStopOnIdleEnd = $true
            $settings.ExecutionTimeLimit = "PT0S"
            $settings.MultipleInstances = 1
            $settings.DisallowStartIfOnBatteries = $false
            $settings.StopIfGoingOnBatteries = $false
            $settings.WakeToRun = $false
            Set-ScheduledTask -TaskName $TaskName -Settings $settings | Out-Null
            Write-Host "Settings auto-restart (999x / 1 menit) diterapkan" -ForegroundColor Green
        } catch { Write-Host "Skip settings tweak: $($_.Exception.Message)" -ForegroundColor Yellow }
    }
} else {
    Write-Host "Bukan Admin: Task Scheduler butuh elevasi -- SKIP (akan pakai Registry+Startup fallback yang tidak butuh admin)" -ForegroundColor Yellow
    Write-Host "Tip: jalankan sekali sebagai Admin untuk dapat Task Scheduler: klik kanan PowerShell -> Run as Administrator -> .\scripts\install_autostart.ps1" -ForegroundColor Gray
}

# 2b) Registry Run (TANPA admin, paling ampuh di Atlas OS) -- lapis utama untuk non-admin
try {
    $regVal = "$psExe $actionArg"
    # Gunakan nama TaskName agar rapi di Task Manager Startup tab
    Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name $TaskName -Value $regVal -Force
    Write-Host "Registry Run dibuat: HKCU\...\Run\$TaskName = $regVal" -ForegroundColor Green
} catch { Write-Host "Gagal buat Registry Run: $($_.Exception.Message)" -ForegroundColor Yellow }

# 3) Fallback Startup folder (lapis kedua — jalan meski Task Scheduler gagal)
try {
    $startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
    $wsh = New-Object -ComObject WScript.Shell
    $lnkPath = Join-Path $startupDir "TelegramBridge.lnk"
    $shortcut = $wsh.CreateShortcut($lnkPath)
    $shortcut.TargetPath = $psExe
    $shortcut.Arguments = $actionArg
    $shortcut.WorkingDirectory = $BridgeDir
    $shortcut.WindowStyle = 7  # minimized
    $shortcut.Description = "Telegram Opencode Bridge Auto-Start"
    $shortcut.Save()
    Write-Host "Startup shortcut dibuat: $lnkPath" -ForegroundColor Green
} catch {
    Write-Host "Gagal buat startup shortcut: $($_.Exception.Message)" -ForegroundColor Yellow
}

# 4) Jalankan sekarang (coba Task, fallback langsung start runner)
Write-Host "`n=== Menjalankan sekarang ===" -ForegroundColor Cyan
if ($taskCreated) {
    schtasks /Run /TN $TaskName 2>&1 | Write-Host
    Start-Sleep -Seconds 3
    schtasks /Query /TN $TaskName /V /FO LIST 2>&1 | Select-String -Pattern "TaskName|Status|Last Run|Next Run|Last Result" | Select-Object -First 20 | Write-Host
} else {
    Write-Host "Task tidak ada (non-admin) -- start runner langsung via Registry/Startup fallback..." -ForegroundColor Gray
    # Cek apakah runner sudah jalan, jika belum start sekarang
    $already = Get-CimInstance Win32_Process -Filter "name='powershell.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*run_bridge_loop.ps1*" }
    if (-not $already) {
        Write-Host "Starter runner manual..." -ForegroundColor Cyan
        $stdoutTmp = Join-Path $env:TEMP "telegram-bridge\runner_out.log"
        $stderrTmp = Join-Path $env:TEMP "telegram-bridge\runner_err.log"
        Start-Process -FilePath $psExe -ArgumentList $actionArg -WorkingDirectory $BridgeDir -WindowStyle Hidden -RedirectStandardOutput $stdoutTmp -RedirectStandardError $stderrTmp | Out-Null
        Write-Host "Runner di-start (PID hidden, cek log)" -ForegroundColor Green
    } else {
        Write-Host "Runner sudah jalan: $($already.ProcessId)" -ForegroundColor Green
    }
    Start-Sleep -Seconds 2
}

# Verifikasi
Write-Host "`n=== Verifikasi ===" -ForegroundColor Cyan
if ($taskCreated) {
    schtasks /Query /TN $TaskName /V /FO LIST 2>&1 | Select-String -Pattern "TaskName|Status|Last Run|Next Run|Last Result" | Select-Object -First 20 | Write-Host
}
# Cek Registry & Startup
$regCheck = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name $TaskName -ErrorAction SilentlyContinue
if ($regCheck) { Write-Host "Registry Run: OK -> $($regCheck.$TaskName)" -ForegroundColor Green } else { Write-Host "Registry Run: TIDAK ADA" -ForegroundColor Yellow }
$lnkCheck = Test-Path (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\TelegramBridge.lnk")
Write-Host "Startup LNK: $lnkCheck" -ForegroundColor $(if($lnkCheck){"Green"}else{"Yellow"})
Write-Host ""
Get-CimInstance Win32_Process -Filter "name='powershell.exe' or name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*run_bridge*" -or $_.CommandLine -like "*bot_bridge_live*" } | Select-Object ProcessId,CommandLine | Format-List | Out-String | Write-Host

Write-Host "`nSelesai. Log ada di: $(Join-Path $env:TEMP 'telegram-bridge\bridge.log')" -ForegroundColor Green
Write-Host "Cek: Get-Content `$env:TEMP\telegram-bridge\bridge.log -Tail 30" -ForegroundColor Gray
Write-Host "Stop: schtasks /End /TN `"$TaskName`"  atau  New-Item -ItemType File -Path `$env:TEMP\telegram-bridge\STOP" -ForegroundColor Gray
Write-Host "Uninstall: .\scripts\install-autostart.ps1 -Uninstall" -ForegroundColor Gray
