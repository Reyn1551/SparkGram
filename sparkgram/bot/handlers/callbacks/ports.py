"""Ports callbacks (port:) — extracted from callbacks.py"""
from telegram.constants import ParseMode


async def handle(query, context, chat_id: int, work_dir: str, payload: str) -> bool:
    from ....engine.port_manager import port_manager
    payload = payload.strip()

    if payload == "list":
        await query.answer("🔄 Refreshing ports...")
        text, kb = port_manager.build_ports_ui()
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True

    if payload.startswith("kill:"):
        port_str = payload[5:]
        if port_str.isdigit():
            port_num = int(port_str)
            ok, msg, _ = port_manager.kill_port(port_num)
            await query.answer("🛑 Port dimatikan!" if ok else "❌ Gagal mematikan port", show_alert=True)
            text, kb = port_manager.build_ports_ui()
            try:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
        return True

    return False
