"""
Local Port & Process Management Service for SparkGram.
Scans active listening dev ports and terminates zombie dev servers cleanly.
"""
import os
import html
import logging
from typing import Dict, List, Optional, Tuple, Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

log = logging.getLogger(__name__)

COMMON_WEB_PORTS = {3000, 5173, 8000, 8080, 8501, 4200, 5000, 8888, 80, 443}


class PortManagerService:
    """Manages active TCP listening ports and clean process termination."""

    @staticmethod
    def get_listening_ports() -> List[Dict[str, Any]]:
        """Scans host machine for active listening TCP ports using psutil."""
        import psutil
        ports_map: Dict[int, Dict[str, Any]] = {}

        try:
            connections = psutil.net_connections(kind="inet")
        except Exception as e:
            log.error(f"Failed to scan net_connections: {e}")
            return []

        for conn in connections:
            if conn.status != "LISTEN" or not conn.laddr:
                continue

            port = conn.laddr.port
            ip = conn.laddr.ip
            pid = conn.pid

            if port in ports_map:
                continue

            p_name = "System/Unknown"
            cmdline = ""
            mem_mb = 0.0

            if pid:
                try:
                    proc = psutil.Process(pid)
                    p_name = proc.name()
                    mem_mb = proc.memory_info().rss / (1024 * 1024)
                    raw_cmd = proc.cmdline()
                    cmdline = " ".join(raw_cmd) if raw_cmd else ""
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            ports_map[port] = {
                "port": port,
                "ip": ip,
                "pid": pid,
                "process_name": p_name,
                "cmdline": cmdline,
                "memory_mb": mem_mb,
                "is_web": port in COMMON_WEB_PORTS or "node" in p_name.lower() or "python" in p_name.lower() or "uvicorn" in p_name.lower(),
            }

        # Sort ports: web/dev ports first, then by port number
        sorted_ports = sorted(
            ports_map.values(),
            key=lambda x: (not x["is_web"], x["port"])
        )
        return sorted_ports

    @classmethod
    def kill_port(cls, port: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Terminates the process tree listening on specified port."""
        import psutil
        listening = cls.get_listening_ports()
        target = next((p for p in listening if p["port"] == port), None)

        if not target or not target.get("pid"):
            return False, f"Tidak ada proses yang sedang mendengarkan pada port <code>{port}</code>.", None

        pid = target["pid"]
        proc_name = target["process_name"]

        try:
            parent = psutil.Process(pid)
            # Find all child processes
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except Exception:
                    pass
            parent.kill()
            psutil.wait_procs(children + [parent], timeout=3)
            return True, f"✅ Proses <b>{html.escape(proc_name)}</b> (PID <code>{pid}</code>) pada port <b>{port}</b> berhasil dimatikan.", target
        except psutil.NoSuchProcess:
            return True, f"Proses pada port <b>{port}</b> sudah tidak aktif.", target
        except Exception as e:
            # Fallback to taskkill on Windows if needed
            if os.name == "nt":
                try:
                    os.system(f"taskkill /F /PID {pid} /T >nul 2>&1")
                    return True, f"✅ Port <b>{port}</b> (PID <code>{pid}</code>) berhasil dimatikan via taskkill.", target
                except Exception as ex:
                    return False, f"Gagal mematikan proses: {ex}", target
            return False, f"Gagal mematikan proses pada port {port}: {e}", target

    @classmethod
    def build_ports_ui(cls) -> Tuple[str, InlineKeyboardMarkup]:
        """Builds Telegram HTML overview card and action buttons for active ports."""
        ports = cls.get_listening_ports()

        if not ports:
            text = (
                "🔌 <b>Local Port & Process Manager</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "<i>Tidak ada port TCP lokal yang sedang mendengarkan (LISTEN).</i>\n"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh Ports", callback_data="port:list")],
                [InlineKeyboardButton("🗑️ Tutup", callback_data="act:close")]
            ])
            return text, kb

        text = (
            f"🔌 <b>Active Ports on Host PC</b> ({len(ports)} aktif)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        buttons: List[List[InlineKeyboardButton]] = []

        for p in ports[:8]:
            port_num = p["port"]
            p_name = p["process_name"]
            pid = p["pid"] or "N/A"
            mem = f"{p['memory_mb']:.1f} MB" if p['memory_mb'] > 0 else ""
            ip = p["ip"]
            is_web = p["is_web"]

            icon = "🌐" if is_web else "🔌"
            text += f"{icon} <b>Port {port_num}</b> ({ip})\n"
            text += f"   • Proses: <code>{html.escape(p_name)}</code> (PID: <code>{pid}</code>) {mem}\n\n"

            # Create action buttons for this port
            row = [
                InlineKeyboardButton(f"🛑 Kill :{port_num}", callback_data=f"port:kill:{port_num}")
            ]
            if is_web:
                row.append(InlineKeyboardButton(f"📸 Preview :{port_num}", callback_data=f"pw:vw:{port_num}:desktop"))
            buttons.append(row)

        if len(ports) > 8:
            text += f"<i>...dan {len(ports)-8} port background lainnya.</i>\n\n"

        text += "━━━━━━━━━━━━━━━━━━━━━━━━━━"

        # Bottom row
        buttons.append([
            InlineKeyboardButton("🔄 Refresh Ports", callback_data="port:list"),
            InlineKeyboardButton("🗑️ Tutup", callback_data="act:close")
        ])

        return text, InlineKeyboardMarkup(buttons)


port_manager = PortManagerService()
