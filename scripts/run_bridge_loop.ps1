# Telegram Opencode Bridge -- Self-Healing Runner v2 (fixed auto-restart)
# Fixes: stream redirect (anti-hang), single-instance mutex, stale killer, watchdog, health log
param()
$ErrorActionPreference = "Continue"
$env:PYTHONUNBUFFERED = "1"
$BridgeDir = "C:\Users\Reynboo\telegram-opencode-bridge"
$PythonExe = "C:\Users\Reynboo\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if (-not (Test-Path $PythonExe)) { $PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not (Test-Path $PythonExe)) { $PythonExe = "python" }
if ($PythonExe -like "*WindowsApps*") {
    $alt = "C:\Users\Reynboo\AppData\Local\Python\pythoncore-3.14-64\python.exe"
    if (Test-Path $alt) { $PythonExe = $alt }
}
$ScriptFile = Join-Path $BridgeDir "bot_bridge_live.py"
$LogDir = Join-Path $env:TEMP "telegram-bridge"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$LogFile = Join-Path $LogDir "bridge.log"
$PidFile = Join-Path $LogDir "bridge.pid"
$ChildPidFile = Join-Path $LogDir "bridge-child.pid"
$LockFile = Join-Path $LogDir "runner.lock"
$StdOutLog = Join-Path $LogDir "child_stdout.log"
$StdErrLog = Join-Path $LogDir "child_stderr.log"

try {
    $lockStream = [System.IO.File]::Open($LockFile, 'OpenOrCreate', 'ReadWrite', 'None')
    try { $lockStream.Lock(0, 1) } catch {
        $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $LogFile -Value "[$ts] Runner lain sudah jalan (lock gagal) -- exit. Hapus $LockFile jika stale."
        Write-Host "Runner lain sudah jalan, exit." -ForegroundColor Yellow
        $lockStream.Close(); $lockStream.Dispose()
        exit 0
    }
} catch { Write-Host "Lock warning: $($_.Exception.Message)" -ForegroundColor Yellow }

$PID | Set-Content $PidFile -Force
"$PID" | Set-Content (Join-Path $LogDir "runner.pid") -Force

function Test-Opencode {
    try { $null = Get-Command opencode -ErrorAction Stop; return $true } catch { return $false }
}

function Kill-StaleBridges {
    $myPid = $PID
    $childPidNow = $null
    if (Test-Path $ChildPidFile) { try { $childPidNow = [int](Get-Content $ChildPidFile -ErrorAction SilentlyContinue) } catch {} }
    $procs = Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue
    foreach ($p in $procs) {
        $cmd = $p.CommandLine
        if (-not $cmd -or $cmd -notlike "*bot_bridge*") { continue }
        $pidToCheck = $p.ProcessId
        if ($pidToCheck -eq $myPid -or $pidToCheck -eq $childPidNow) { continue }
        if ($p.ParentProcessId -eq $myPid) { continue }
        $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $msg = "[$ts] Killing stale bridge PID=$pidToCheck (PPid=$($p.ParentProcessId)) Cmd=$cmd"
        Write-Host $msg -ForegroundColor Magenta
        Add-Content -Path $LogFile -Value $msg
        try { Stop-Process -Id $pidToCheck -Force -ErrorAction SilentlyContinue } catch {}
        try { cmd /c "taskkill /F /T /PID $pidToCheck" 2>$null | Out-Null } catch {}
    }
}

Kill-StaleBridges

$restartCount = 0
$maxBackoff = 5
while ($true) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $msg = "[$timestamp] Starting bridge (attempt #$($restartCount+1)) -- $PythonExe $ScriptFile"
    Write-Host $msg -ForegroundColor Green
    Add-Content -Path $LogFile -Value $msg
    if (-not (Test-Opencode)) {
        $warn = "[$timestamp] WARNING: opencode tidak di PATH -- bridge tetap jalan tapi LLM call mungkin gagal"
        Write-Host $warn -ForegroundColor Yellow
        Add-Content -Path $LogFile -Value $warn
    }
    if (-not (Test-Path (Join-Path $BridgeDir ".env"))) {
        $warn = "[$timestamp] WARNING: .env tidak ditemukan di $BridgeDir"
        Add-Content -Path $LogFile -Value $warn
    }
    Kill-StaleBridges
    try {
        $stdout = $StdOutLog
        $stderr = $StdErrLog
        try { Remove-Item $stdout -Force -ErrorAction SilentlyContinue } catch {}
        try { Remove-Item $stderr -Force -ErrorAction SilentlyContinue } catch {}
        $proc = Start-Process -FilePath $PythonExe -ArgumentList "`"$ScriptFile`"" -WorkingDirectory $BridgeDir -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        "$($proc.Id)" | Set-Content $ChildPidFile -Force
        Add-Content -Path $LogFile -Value "[$timestamp] Child PID=$($proc.Id) started (stdout=$stdout)"
        # Normal event-driven wait: only react if process exits or STOP file is created
        while (-not $proc.HasExited) {
            Start-Sleep -Seconds 2
            if (Test-Path (Join-Path $LogDir "STOP")) { 
                try { $proc.Kill() } catch {}
                break 
            }
        }
        try { $proc.WaitForExit(5000) | Out-Null } catch {}
        $exitCode = $proc.ExitCode
        if ($null -eq $exitCode) { $exitCode = -1 }
        $timestamp2 = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $isIntentional = ($exitCode -eq 0)
        if ($isIntentional) {
            $msg2 = "[$timestamp2] Bridge stopped intentional (code 0, watchdog/manual restart) -- will restart clean"
            Write-Host $msg2 -ForegroundColor Green
        } else {
            $msg2 = "[$timestamp2] Bridge exited with code $exitCode (unexpected -- check tail)"
            Write-Host $msg2 -ForegroundColor Yellow
        }
        Add-Content -Path $LogFile -Value $msg2
        try {
            if (-not $isIntentional) {
                if (Test-Path $stderr) {
                    $tail = Get-Content $stderr -Tail 15 -ErrorAction SilentlyContinue | Out-String
                    if ($tail.Trim()) { Add-Content -Path $LogFile -Value "--- stderr tail ---`n$tail`n--- end ---" }
                }
                if (Test-Path $stdout) {
                    $tail2 = Get-Content $stdout -Tail 12 -ErrorAction SilentlyContinue | Out-String
                    # filter noisy SystemExit tail for intentional restarts (already handled)
                    if ($tail2.Trim() -and $tail2 -notmatch "SystemExit") { Add-Content -Path $LogFile -Value "--- stdout tail ---`n$tail2`n--- end ---" }
                }
            } else {
                # intentional: only log 3 lines for audit, no error tail
                if (Test-Path $stdout) {
                    $tail2 = Get-Content $stdout -Tail 3 -ErrorAction SilentlyContinue | Out-String
                    if ($tail2.Trim()) { Add-Content -Path $LogFile -Value "--- intentional restart tail ---`n$tail2`n--- end ---" }
                }
            }
        } catch {}
    } catch {
        $timestamp2 = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $err = "[$timestamp2] Runner exception: $($_.Exception.Message)"
        Write-Host $err -ForegroundColor Red
        Add-Content -Path $LogFile -Value $err
        $exitCode = 1
    }
    $restartCount++
    # STABIL: capped 5s flat (dulu 5→60s bikin mati 60 detik) — env MAX_BACKOFF override jika perlu
    # Fix: intentional exit 0 tidak dihitung sebagai crash (reset backoff lebih lambat)
    if ($env:MAX_BACKOFF) { $maxBackoff = [int]$env:MAX_BACKOFF }
    if ($isIntentional -and $restartCount -lt 50) {
        $sleepSec = 2  # watchdog restart cepat, bukan error
    } else {
        $sleepSec = 5
        if ($restartCount -gt 10) { $sleepSec = $maxBackoff }
    }
    $stopSignal = Join-Path $LogDir "STOP"
    if (Test-Path $stopSignal) {
        Add-Content -Path $LogFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] STOP signal detected -- tidak restart lagi"
        Remove-Item $stopSignal -Force -ErrorAction SilentlyContinue
        break
    }
    $msg3 = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Restart dalam ${sleepSec}s... (restart #$restartCount, log: $LogFile)"
    Write-Host $msg3 -ForegroundColor Cyan
    Add-Content -Path $LogFile -Value $msg3
    Start-Sleep -Seconds $sleepSec
    try {
        if ((Get-Item $LogFile -ErrorAction SilentlyContinue).Length -gt 5MB) {
            $old = "$LogFile.old"
            Move-Item $LogFile $old -Force -ErrorAction SilentlyContinue
            Add-Content -Path $LogFile -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Log rotated"
        }
    } catch {}
}
