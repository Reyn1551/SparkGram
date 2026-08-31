"""
Cross-Platform Service and Unit Generators for SparkGram.
Generates Linux systemd unit, Windows NSSM script, and container specifications.
"""
import os
import sys
from pathlib import Path


def generate_systemd_unit(install_dir: str, python_bin: str) -> str:
    """Generates production-grade Linux systemd service unit."""
    return f"""[Unit]
Description=SparkGram Telegram AI Live Bridge Service
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={install_dir}
ExecStart={python_bin} -m sparkgram
Restart=always
RestartSec=3s
WatchdogSec=30s
MemoryMax=512M
ProtectSystem=full
NoNewPrivileges=true
KillMode=mixed
TimeoutStopSec=10s

[Install]
WantedBy=multi-user.target
"""


def generate_windows_nssm_script(install_dir: str, python_exe: str, service_name: str = "SparkGramBridge") -> str:
    """Generates PowerShell script to register SparkGram as Windows Service via NSSM."""
    return f"""# SparkGram Windows Service Installer via NSSM
$ServiceName = "{service_name}"
$PythonExe = "{python_exe}"
$AppDir = "{install_dir}"

nssm install $ServiceName $PythonExe "-m sparkgram"
nssm set $ServiceName AppDirectory $AppDir
nssm set $ServiceName AppStdout "$AppDir\\logs\\service_stdout.log"
nssm set $ServiceName AppStderr "$AppDir\\logs\\service_stderr.log"
nssm set $ServiceName AppRotateFiles 1
nssm set $ServiceName AppRotateBytes 10485760
nssm set $ServiceName AppRestartDelay 3000
nssm start $ServiceName
Write-Host "✅ SparkGram Windows Service successfully configured and started." -ForegroundColor Green
"""
