# SparkGram autostart via schtasks
$taskName = "SparkGramBridge"
$bridgeDir = "C:\Users\Reynboo\telegram-opencode-bridge"
$loopScript = Join-Path $bridgeDir "scripts\run_bridge_loop.ps1"
if (-not (Test-Path $loopScript)) { Write-Error "Loop not found"; exit 1 }
schtasks /delete /tn $taskName /f 2>$null | Out-Null
$tr = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\Reynboo\telegram-opencode-bridge\scripts\run_bridge_loop.ps1"'
$result = schtasks /create /tn $taskName /tr "$tr" /sc onlogon /rl HIGHEST /f 2>&1
Write-Host $result
schtasks /query /tn $taskName 2>&1 | Select-Object -First 5 | Write-Host
Write-Host "installed"
schtasks /run /tn $taskName 2>&1 | Write-Host
