"""
System and Host PC/Laptop Health Monitor for SparkGram.
Provides full telemetry for Host PC/Laptop (CPU, RAM, Disk, Battery, GPU, Process Uptime).
"""
import os
import sys
import time
import shutil
import platform
import datetime
import subprocess
import html
from pathlib import Path
from typing import Dict, Any, Optional, List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..config import settings


def render_bar(percent: float, width: int = 10) -> str:
    """Renders a text progress bar like [█████░░░░░] 50%."""
    clamped = max(0.0, min(100.0, float(percent)))
    filled_len = int(round(width * clamped / 100))
    empty_len = width - filled_len
    bar = "█" * filled_len + "░" * empty_len
    return f"<code>[{bar}] {clamped:.1f}%</code>"


def get_system_health() -> Dict[str, Any]:
    """Collects comprehensive hardware and process metrics from host PC/Laptop."""
    data: Dict[str, Any] = {
        "hostname": platform.node() or "Unknown-Host",
        "platform": f"{platform.system()} {platform.release()} ({platform.machine()})",
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count() or 1,
        "cpu_percent": 0.0,
        "cpu_model": platform.processor() or "CPU",
        "ram_total_gb": 0.0,
        "ram_used_gb": 0.0,
        "ram_percent": 0.0,
        "disk_total_gb": 0.0,
        "disk_used_gb": 0.0,
        "disk_percent": 0.0,
        "battery_percent": None,
        "battery_plugged": None,
        "gpu_name": None,
        "gpu_vram_total_mb": None,
        "gpu_vram_used_mb": None,
        "gpu_temp_c": None,
        "gpu_util_percent": None,
        "uptime_str": "Unknown",
        "process_pid": os.getpid(),
        "process_ram_mb": 0.0,
        "process_uptime_sec": 0.0,
    }

    # 1. Collect metrics via psutil if available
    try:
        import psutil
        # Boot time & Uptime
        boot_dt = datetime.datetime.fromtimestamp(psutil.boot_time())
        diff = datetime.datetime.now() - boot_dt
        days, rem = divmod(int(diff.total_seconds()), 86400)
        hours, rem = divmod(rem, 3600)
        mins, _ = divmod(rem, 60)
        data["uptime_str"] = f"{days}h {hours}j {mins}m" if days > 0 else f"{hours} jam {mins} menit"

        # CPU
        data["cpu_percent"] = psutil.cpu_percent(interval=0.1)

        # RAM
        vmem = psutil.virtual_memory()
        data["ram_total_gb"] = vmem.total / (1024 ** 3)
        data["ram_used_gb"] = vmem.used / (1024 ** 3)
        data["ram_percent"] = vmem.percent

        # Disk C:
        root_path = "C:\\" if sys.platform == "win32" else "/"
        du = shutil.disk_usage(root_path)
        data["disk_total_gb"] = du.total / (1024 ** 3)
        data["disk_used_gb"] = (du.total - du.free) / (1024 ** 3)
        data["disk_percent"] = (data["disk_used_gb"] / max(1.0, data["disk_total_gb"])) * 100

        # Battery
        bat = psutil.sensors_battery()
        if bat:
            data["battery_percent"] = bat.percent
            data["battery_plugged"] = bat.power_plugged

        # Process RAM (RSS)
        proc = psutil.Process(os.getpid())
        data["process_ram_mb"] = proc.memory_info().rss / (1024 * 1024)
        data["process_uptime_sec"] = time.time() - proc.create_time()

    except Exception:
        # Fallback using standard library
        try:
            root_path = "C:\\" if sys.platform == "win32" else "/"
            du = shutil.disk_usage(root_path)
            data["disk_total_gb"] = du.total / (1024 ** 3)
            data["disk_used_gb"] = (du.total - du.free) / (1024 ** 3)
            data["disk_percent"] = (data["disk_used_gb"] / max(1.0, data["disk_total_gb"])) * 100
        except Exception:
            pass

    # 2. Collect GPU metrics via nvidia-smi if present
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        try:
            out = subprocess.check_output(
                [nvidia_smi, "--query-gpu=name,memory.total,memory.used,temperature.gpu,utilization.gpu", "--format=csv,noheader,nounits"],
                text=True,
                timeout=2.0
            ).strip()
            if out:
                parts = [p.strip() for p in out.split(",")]
                if len(parts) >= 5:
                    data["gpu_name"] = parts[0]
                    data["gpu_vram_total_mb"] = float(parts[1]) if parts[1].isdigit() else None
                    data["gpu_vram_used_mb"] = float(parts[2]) if parts[2].isdigit() else None
                    data["gpu_temp_c"] = float(parts[3]) if parts[3].isdigit() else None
                    data["gpu_util_percent"] = float(parts[4]) if parts[4].isdigit() else None
        except Exception:
            pass

    return data


def format_health_html(data: Dict[str, Any], active_session: Optional[str] = None, is_busy: bool = False) -> str:
    """Formats telemetry data into Telegram HTML layout."""
    host = html.escape(str(data["hostname"]))
    platform_info = html.escape(str(data["platform"]))
    uptime = html.escape(str(data["uptime_str"]))
    
    cpu_bar = render_bar(data["cpu_percent"])
    ram_bar = render_bar(data["ram_percent"])
    disk_bar = render_bar(data["disk_percent"])

    # Battery
    battery_line = ""
    if data["battery_percent"] is not None:
        bat_icon = "🔌 AC Charger" if data["battery_plugged"] else "🔋 Baterai"
        bat_pct = data["battery_percent"]
        battery_line = f"• <b>Power/Baterai:</b> {bat_icon} ({bat_pct}%)\n"

    # GPU
    gpu_line = ""
    if data["gpu_name"]:
        gpu_name = html.escape(data["gpu_name"])
        temp_str = f" • 🌡️ {data['gpu_temp_c']:.0f}°C" if data["gpu_temp_c"] is not None else ""
        vram_str = f" • VRAM: {data['gpu_vram_used_mb']:.0f}/{data['gpu_vram_total_mb']:.0f} MB" if data["gpu_vram_total_mb"] else ""
        gpu_line = f"• <b>GPU:</b> <code>{gpu_name}</code>{temp_str}{vram_str}\n"

    # Bridge status
    ses_str = f"<code>{html.escape(active_session)}</code>" if active_session else "<i>(tidak ada)</i>"
    task_status = "🏃 <b>Sibuk (Job Running)</b>" if is_busy else "🟢 <b>Idle (Siap)</b>"
    proc_uptime_mins = int(data["process_uptime_sec"] / 60)

    text = (
        f"🏥 <b>Status Kesehatan Host & Companion PC</b>\n\n"
        f"🖥️ <b>Host:</b> <code>{host}</code>\n"
        f"💻 <b>OS:</b> <code>{platform_info}</code>\n"
        f"⏱️ <b>Uptime Host:</b> <code>{uptime}</code>\n\n"
        f"⚙️ <b>CPU ({data['cpu_count']} Cores):</b>\n"
        f"   {cpu_bar}\n\n"
        f"🧠 <b>RAM ({data['ram_used_gb']:.1f} GB / {data['ram_total_gb']:.1f} GB):</b>\n"
        f"   {ram_bar}\n\n"
        f"💾 <b>Disk C: ({data['disk_used_gb']:.1f} GB / {data['disk_total_gb']:.1f} GB):</b>\n"
        f"   {disk_bar}\n\n"
        f"{battery_line}"
        f"{gpu_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>SparkGram Bridge Daemon:</b>\n"
        f"• Status: {task_status}\n"
        f"• Model: <code>{html.escape(settings.runtime_model)}</code>\n"
        f"• Session: {ses_str}\n"
        f"• Memory Bridge: <code>{data['process_ram_mb']:.1f} MB</code> (PID {data['process_pid']})\n"
        f"• Bridge Uptime: <code>{proc_uptime_mins} menit</code>\n"
        f"• WorkDir: <code>{html.escape(settings.runtime_work_dir)}</code>"
    )
    return text


def build_health_keyboard() -> InlineKeyboardMarkup:
    """Builds interactive action bar for /health message."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Refresh Telemetri", callback_data="hlth:refresh"),
            InlineKeyboardButton("🤖 Ganti Model", callback_data="hlth:model"),
        ],
        [
            InlineKeyboardButton("📁 Switch Session", callback_data="sw:refresh"),
            InlineKeyboardButton("📜 Tail Logs", callback_data="hlth:logs"),
        ]
    ])
