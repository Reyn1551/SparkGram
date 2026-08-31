"""
Companion PC Health Collector for SparkGram.
Cross-platform (Windows/Linux/macOS), psutil-accelerated, stdlib fallback.
"""
import os
import sys
import time
import html
import shutil
import socket
import platform
import logging
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

log = logging.getLogger(__name__)

# Bot start timestamp for uptime calc (set on import)
_BOT_START = time.monotonic()
_BOT_START_WALL = time.time()

try:
    import psutil  # type: ignore
    HAS_PSUTIL = True
except ImportError:
    psutil = None  # type: ignore
    HAS_PSUTIL = False

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _bar(percent: float, width: int = 10) -> str:
    """Block progress bar e.g. █████░░░░░ 52%"""
    filled = int(round(percent / 100 * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled) + f" {percent:.0f}%"


def _status_emoji(percent: float, warn: float = 75, crit: float = 90) -> str:
    if percent >= crit:
        return "🔴"
    if percent >= warn:
        return "🟡"
    return "🟢"


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def _fmt_duration(sec: float) -> str:
    sec = int(sec)
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{d}d")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if s or not parts:
        parts.append(f"{s}s")
    return " ".join(parts)


def _safe_nvidia_smi() -> Optional[Dict[str, Any]]:
    """Try nvidia-smi query, return dict or None."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            timeout=3,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        ).strip()
        if not out:
            return None
        # first GPU only for brevity
        first = out.splitlines()[0].split(",")
        # fields: name, mem_total MiB, mem_used MiB, util %, temp C
        return {
            "name": first[0].strip(),
            "mem_total_mib": float(first[1].strip()),
            "mem_used_mib": float(first[2].strip()),
            "util": float(first[3].strip()),
            "temp_c": float(first[4].strip()) if first[4].strip().isdigit() else None,
        }
    except Exception:
        return None


def _disk_partitions() -> List[Dict[str, Any]]:
    """Collect disk usage for each mount/drive."""
    result: List[Dict[str, Any]] = []
    if HAS_PSUTIL:
        try:
            for part in psutil.disk_partitions(all=False):
                # skip empty / snap on linux
                if "snap" in part.mountpoint or part.fstype == "":
                    continue
                try:
                    u = psutil.disk_usage(part.mountpoint)
                    result.append({
                        "mount": part.mountpoint,
                        "fstype": part.fstype,
                        "total": u.total,
                        "used": u.used,
                        "free": u.free,
                        "percent": u.percent,
                    })
                except Exception:
                    continue
            if result:
                return result
        except Exception as e:
            log.debug(f"Disk psutil fallback skip: {e}")
    # Fallback: check common mounts/drives
    candidates: List[str] = []
    if os.name == "nt":
        # Windows drives C:\, D:\ ...
        import string
        for letter in string.ascii_uppercase:
            d = f"{letter}:\\"
            if os.path.exists(d):
                candidates.append(d)
    else:
        candidates = ["/"]
        # also check /home if separate
        if os.path.exists("/home"):
            candidates.append("/home")
    for m in candidates:
        try:
            total, used, free = shutil.disk_usage(m)
            pct = (used / total * 100) if total else 0
            result.append({"mount": m, "fstype": "?", "total": total, "used": used, "free": free, "percent": pct})
        except Exception:
            continue
    return result


# ---------------------------------------------------------------------------
# main collector
# ---------------------------------------------------------------------------

def get_health_snapshot() -> Dict[str, Any]:
    """Gather health metrics, never raises — returns dict."""
    snap: Dict[str, Any] = {}
    now = time.time()

    # --- platform ---
    snap["hostname"] = socket.gethostname()
    snap["os"] = f"{platform.system()} {platform.release()} ({platform.version()[:40]})"
    snap["os_short"] = f"{platform.system()} {platform.release()}"
    snap["arch"] = platform.machine()
    snap["python"] = platform.python_version()
    snap["has_psutil"] = HAS_PSUTIL

    # --- uptime ---
    snap["bot_uptime_sec"] = time.monotonic() - _BOT_START
    snap["bot_started"] = _BOT_START_WALL
    if HAS_PSUTIL:
        try:
            snap["boot_time"] = psutil.boot_time()
            snap["sys_uptime_sec"] = now - psutil.boot_time()
        except Exception:
            snap["sys_uptime_sec"] = snap["bot_uptime_sec"]
    else:
        snap["sys_uptime_sec"] = snap["bot_uptime_sec"]
        snap["boot_time"] = now - snap["sys_uptime_sec"]

    # --- cpu ---
    if HAS_PSUTIL:
        try:
            snap["cpu_percent"] = psutil.cpu_percent(interval=0.4)
            snap["cpu_count_logical"] = psutil.cpu_count(logical=True)
            snap["cpu_count_physical"] = psutil.cpu_count(logical=False)
            freq = psutil.cpu_freq()
            snap["cpu_freq_mhz"] = freq.current if freq else None
            snap["cpu_freq_max"] = freq.max if freq else None
            snap["load_avg"] = list(os.getloadavg()) if hasattr(os, "getloadavg") else None
            snap["cpu_name"] = platform.processor() or "Unknown CPU"
        except Exception as e:
            log.debug(f"cpu collect fail: {e}")
            snap["cpu_percent"] = 0
    else:
        snap["cpu_percent"] = 0
        snap["cpu_count_logical"] = os.cpu_count() or 0
        snap["cpu_count_physical"] = os.cpu_count() or 0
        snap["cpu_freq_mhz"] = None
        snap["cpu_name"] = platform.processor() or "Unknown CPU"
        snap["load_avg"] = list(os.getloadavg()) if hasattr(os, "getloadavg") else None

    # refine cpu name on Windows via wmic fallback if empty
    if not snap.get("cpu_name") or snap["cpu_name"] in ("", "Unknown CPU"):
        try:
            if os.name == "nt":
                out = subprocess.check_output(
                    ["wmic", "cpu", "get", "name"], timeout=3, text=True, stderr=subprocess.DEVNULL
                )
                lines = [l.strip() for l in out.splitlines() if l.strip() and "Name" not in l]
                if lines:
                    snap["cpu_name"] = lines[0]
        except Exception as e:
            log.debug(f"WMIC cpu name skip: {e}")

    # --- memory ---
    if HAS_PSUTIL:
        try:
            vm = psutil.virtual_memory()
            snap["ram_total"] = vm.total
            snap["ram_available"] = vm.available
            snap["ram_used"] = vm.used
            snap["ram_percent"] = vm.percent
            sm = psutil.swap_memory()
            snap["swap_total"] = sm.total
            snap["swap_used"] = sm.used
            snap["swap_percent"] = sm.percent
        except Exception:
            snap["ram_total"] = snap["ram_used"] = snap["ram_percent"] = 0
    else:
        snap["ram_total"] = snap["ram_used"] = snap["ram_percent"] = 0
        snap["ram_available"] = 0
        snap["swap_total"] = snap["swap_used"] = snap["swap_percent"] = 0

    # --- disk ---
    snap["disks"] = _disk_partitions()

    # --- battery ---
    snap["battery"] = None
    if HAS_PSUTIL:
        try:
            b = psutil.sensors_battery()
            if b is not None:
                snap["battery"] = {
                    "percent": b.percent,
                    "plugged": b.power_plugged,
                    "secsleft": b.secsleft,
                }
        except Exception as e:
            log.debug(f"Battery collect skip: {e}")
    # fallback Windows via WMIC? leave None if unavailable

    # --- gpu ---
    snap["gpu"] = _safe_nvidia_smi()

    # --- network ---
    if HAS_PSUTIL:
        try:
            net = psutil.net_io_counters()
            snap["net_sent"] = net.bytes_sent
            snap["net_recv"] = net.bytes_recv
        except Exception:
            snap["net_sent"] = snap["net_recv"] = 0
    else:
        snap["net_sent"] = snap["net_recv"] = 0

    # --- process self ---
    if HAS_PSUTIL:
        try:
            p = psutil.Process(os.getpid())
            snap["proc_mem_rss"] = p.memory_info().rss
            snap["proc_mem_percent"] = p.memory_percent()
            snap["proc_cpu_percent"] = p.cpu_percent(interval=0.2)
            snap["proc_threads"] = p.num_threads()
        except Exception:
            snap["proc_mem_rss"] = 0
            snap["proc_threads"] = 0
    else:
        snap["proc_mem_rss"] = 0
        snap["proc_threads"] = 0

    # --- opencode availability ---
    snap["opencode_available"] = shutil.which("opencode") is not None

    # --- temperatures (linux mostly) ---
    snap["temps"] = {}
    if HAS_PSUTIL:
        try:
            temps = psutil.sensors_temperatures() or {}
            for name, entries in temps.items():
                if entries:
                    snap["temps"][name] = entries[0].current
        except Exception as e:
            log.debug(f"Temps collect skip: {e}")

    snap["collected_at"] = now
    return snap


# ---------------------------------------------------------------------------
# HTML formatters for Telegram (parse_mode HTML)
# ---------------------------------------------------------------------------

def format_health_html(snap: Dict[str, Any], detailed: bool = False) -> str:
    """Main /health card — compact but comprehensive."""
    h = snap.get("hostname", "?")
    bot_up = _fmt_duration(snap.get("bot_uptime_sec", 0))
    sys_up = _fmt_duration(snap.get("sys_uptime_sec", 0))

    cpu_p = snap.get("cpu_percent", 0) or 0
    ram_p = snap.get("ram_percent", 0) or 0
    proc_rss = snap.get("proc_mem_rss", 0) or 0

    # health score heuristic
    worst = max(cpu_p, ram_p, max((d["percent"] for d in snap.get("disks", [])), default=0))
    if worst >= 90 or (snap.get("battery") and snap["battery"]["percent"] is not None and snap["battery"]["percent"] < 15 and not snap["battery"]["plugged"]):
        health_emoji = "🔴"
        health_label = "CRITICAL"
    elif worst >= 75:
        health_emoji = "🟡"
        health_label = "WARNING"
    else:
        health_emoji = "🟢"
        health_label = "HEALTHY"

    lines: List[str] = []
    lines.append(f"{health_emoji} <b>SparkGram Health — {health_label}</b>")
    lines.append(f"<code>{html.escape(h)}</code> • <code>{html.escape(snap.get('os_short',''))}</code> • Python {html.escape(snap.get('python',''))}")
    lines.append(f"⏱️ Bot up: <b>{bot_up}</b>  |  System up: <b>{sys_up}</b>")
    if not snap.get("has_psutil"):
        lines.append(f"<i>⚠️ psutil tidak terpasang — data terbatas. Install: <code>pip install psutil</code></i>")
    lines.append("")

    # CPU
    cpu_bar = _bar(cpu_p)
    lines.append(f"{_status_emoji(cpu_p)} <b>CPU</b> {html.escape(snap.get('cpu_name','')[:38])} ({snap.get('cpu_count_physical','?')}P/{snap.get('cpu_count_logical','?')}T)")
    freq = snap.get("cpu_freq_mhz")
    freq_s = f" @ {freq:.0f}MHz" if freq else ""
    lines.append(f"   <code>{cpu_bar}{freq_s}</code>")
    if snap.get("load_avg"):
        lines.append(f"   loadavg: <code>{snap['load_avg'][0]:.2f} {snap['load_avg'][1]:.2f} {snap['load_avg'][2]:.2f}</code>")

    # RAM
    if snap.get("ram_total"):
        ram_used_s = _fmt_bytes(snap["ram_used"])
        ram_tot_s = _fmt_bytes(snap["ram_total"])
        lines.append(f"{_status_emoji(ram_p)} <b>RAM</b> <code>{_bar(ram_p)}</code>  {ram_used_s} / {ram_tot_s}")
        if snap.get("swap_total"):
            lines.append(f"   swap: <code>{_bar(snap['swap_percent'])}</code> {_fmt_bytes(snap['swap_used'])}/{_fmt_bytes(snap['swap_total'])}")

    # Disks
    for d in snap.get("disks", []):
        pct = d["percent"]
        total_s = _fmt_bytes(d["total"])
        free_s = _fmt_bytes(d["free"])
        mount = html.escape(d["mount"])
        lines.append(f"{_status_emoji(pct, 80, 95)} <b>Disk {mount}</b> <code>{_bar(pct)}</code>  free {free_s} / {total_s}")

    # GPU
    gpu = snap.get("gpu")
    if gpu:
        used_s = _fmt_bytes(gpu["mem_used_mib"] * 1024 * 1024)
        tot_s = _fmt_bytes(gpu["mem_total_mib"] * 1024 * 1024)
        gpu_pct = (gpu["mem_used_mib"] / gpu["mem_total_mib"] * 100) if gpu["mem_total_mib"] else 0
        lines.append(f"🎮 <b>GPU</b> {html.escape(gpu['name'])} — {gpu['util']:.0f}% util, {gpu['temp_c']:.0f}°C" if gpu.get("temp_c") else f"🎮 <b>GPU</b> {html.escape(gpu['name'])} — {gpu['util']:.0f}% util")
        lines.append(f"   VRAM <code>{_bar(gpu_pct)}</code> {used_s}/{tot_s}")

    # Battery
    bat = snap.get("battery")
    if bat and bat["percent"] is not None:
        b_pct = bat["percent"]
        plugged = "🔌 Charging" if bat["plugged"] else "🔋 Battery"
        secs = bat.get("secsleft")
        time_s = ""
        if secs not in (None, -1) and secs >= 0 and not bat["plugged"]:
            time_s = f" (~{_fmt_duration(secs)} left)"
        elif bat["plugged"]:
            time_s = " (AC)"
        lines.append(f"{_status_emoji(100 - b_pct, 50, 85) if not bat['plugged'] else '🔌'} <b>{plugged}</b> <code>{_bar(b_pct)}</code>{time_s}")

    # SparkGram proc
    if proc_rss:
        lines.append(f"🤖 <b>SparkGram</b> RSS {_fmt_bytes(proc_rss)} • threads {snap.get('proc_threads','?')}")

    # opencode
    oc = "✅ tersedia" if snap.get("opencode_available") else "❌ tidak di PATH"
    lines.append(f"⚙️ <b>opencode</b>: {oc}")

    # temps
    if snap.get("temps"):
        t_str = " • ".join(f"{html.escape(k)} {v:.0f}°C" for k, v in list(snap["temps"].items())[:3])
        lines.append(f"🌡️ {t_str}")

    # net
    if snap.get("net_sent"):
        lines.append(f"🌐 Net TX {_fmt_bytes(snap['net_sent'])} / RX {_fmt_bytes(snap['net_recv'])}")

    lines.append("")
    lines.append(f"<i>Updated {time.strftime('%H:%M:%S %d/%m/%Y', time.localtime(snap.get('collected_at', time.time())))}</i>")
    if not detailed:
        lines.append(f"<i>Tap 🔍 Detail untuk info host lengkap</i>")

    return "\n".join(lines)


def format_sysinfo_html(snap: Dict[str, Any]) -> str:
    """Detailed host dump for /sysinfo."""
    lines: List[str] = []
    lines.append(f"🖥️ <b>Companion PC — Detailed SysInfo</b>")
    lines.append(f"Host: <code>{html.escape(snap.get('hostname',''))}</code>")
    lines.append(f"OS: <code>{html.escape(snap.get('os',''))}</code>")
    lines.append(f"Arch: <code>{html.escape(snap.get('arch',''))}</code> • Python {html.escape(snap.get('python',''))}")
    lines.append(f"Uptime: bot <b>{_fmt_duration(snap.get('bot_uptime_sec',0))}</b> • sys <b>{_fmt_duration(snap.get('sys_uptime_sec',0))}</b>")
    lines.append("")
    lines.append(f"<b>CPU:</b> <code>{html.escape(snap.get('cpu_name',''))}</code>")
    lines.append(f"  Cores: {snap.get('cpu_count_physical')}P / {snap.get('cpu_count_logical')}T  •  Freq: {snap.get('cpu_freq_mhz') or '?'} MHz")
    if snap.get("load_avg"):
        lines.append(f"  Loadavg: {snap['load_avg'][0]:.2f} {snap['load_avg'][1]:.2f} {snap['load_avg'][2]:.2f}")
    lines.append("")
    if snap.get("ram_total"):
        lines.append(f"<b>RAM:</b> {_fmt_bytes(snap['ram_used'])}/{_fmt_bytes(snap['ram_total'])} ({snap['ram_percent']:.0f}%) avail {_fmt_bytes(snap.get('ram_available',0))}")
        if snap.get("swap_total"):
            lines.append(f"  Swap: {_fmt_bytes(snap['swap_used'])}/{_fmt_bytes(snap['swap_total'])} ({snap['swap_percent']:.0f}%)")
    for d in snap.get("disks", []):
        lines.append(f"<b>Disk {html.escape(d['mount'])}</b> [{d['fstype']}] {_fmt_bytes(d['used'])}/{_fmt_bytes(d['total'])} ({d['percent']:.0f}%) free {_fmt_bytes(d['free'])}")
    lines.append("")
    gpu = snap.get("gpu")
    if gpu:
        lines.append(f"<b>GPU:</b> {html.escape(gpu['name'])}  util {gpu['util']:.0f}%  VRAM {gpu['mem_used_mib']:.0f}/{gpu['mem_total_mib']:.0f} MiB  temp {gpu.get('temp_c','?')}°C")
    else:
        lines.append(f"<b>GPU:</b> <i>tidak terdeteksi / headless</i>")
    bat = snap.get("battery")
    if bat and bat["percent"] is not None:
        lines.append(f"<b>Battery:</b> {bat['percent']:.0f}% {'(AC ⚡)' if bat['plugged'] else '(DC 🔋)'}  secsleft: {bat.get('secsleft')}")
    else:
        lines.append(f"<b>Battery:</b> <i>Desktop / no battery sensor</i>")
    if snap.get("temps"):
        lines.append(f"<b>Temps:</b> " + " • ".join(f"{html.escape(k)} {v:.0f}°C" for k, v in snap["temps"].items()))
    lines.append(f"<b>Net:</b> TX {_fmt_bytes(snap.get('net_sent',0))} RX {_fmt_bytes(snap.get('net_recv',0))}")
    lines.append(f"<b>Proc RSS:</b> {_fmt_bytes(snap.get('proc_mem_rss',0))} • threads {snap.get('proc_threads','?')}")
    lines.append("")
    lines.append(f"<i>psutil={'✅' if snap.get('has_psutil') else '❌'} • opencode={'✅' if snap.get('opencode_available') else '❌'}</i>")
    return "\n".join(lines)
