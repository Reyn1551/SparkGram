# SparkGram Auto-Restart Loop - PnP anywhere
$ErrorActionPreference = "SilentlyContinue"
$bridgeDir = "C:\Users\Reynboo\telegram-opencode-bridge"
$bridgePy = Join-Path $bridgeDir "bot_bridge_live.py"
$logDir = Join-Path $env:TEMP "sparkgram_logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog = Join-Path $logDir "bridge_out.log"
$errLog = Join-Path $logDir "bridge_err.log"
if (-not (Test-Path (Join-Path $bridgeDir ".env")) -and (Test-Path (Join-Path $bridgeDir ".env.example"))) {
    Copy-Item (Join-Path $bridgeDir ".env.example") (Join-Path $bridgeDir ".env")
}
$mutexName = "Global\SparkGramBridgeMutex"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
if (-not $mutex.WaitOne(0)) {
    Write-Host "SparkGram already running - exiting at $(Get-Date)"
    exit 0
}
Write-Host "SparkGram loop started PID $PID at $(Get-Date) - $bridgePy" | Tee-Object -FilePath $outLog -Append
while ($true) {
    $start = Get-Date
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting bridge..." | Tee-Object -FilePath $outLog -Append
    try {
        $PythonExe = "C:\Users\Reynboo\AppData\Local\Python\pythoncore-3.14-64\python.exe"
        if (-not (Test-Path $PythonExe)) { $PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source }
        if (-not $PythonExe) { $PythonExe = "python" }
        Write-Host "Using python: $PythonExe" | Tee-Object -FilePath $outLog -Append
        $proc = Start-Process -FilePath $PythonExe -ArgumentList "`"$bridgePy`"" -WorkingDirectory $bridgeDir -NoNewWindow -PassThru -Wait
        $code = $proc.ExitCode
        Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Bridge exited code $code" | Tee-Object -FilePath $outLog -Append
        Add-Content -Path $errLog -Value "[$(Get-Date)] exit $code"
    } catch {
        Write-Host "Loop exception: $_" | Tee-Object -FilePath $errLog -Append
    }
    $elapsed = (Get-Date) - $start
    if ($elapsed.TotalSeconds -lt 10) {
        Write-Host "Crash loop - waiting 15s..." | Tee-Object -FilePath $outLog -Append
        Start-Sleep -Seconds 15
    } else {
        Start-Sleep -Seconds 5
    }
    Write-Host "Restarting bridge..." | Tee-Object -FilePath $outLog -Append
}
