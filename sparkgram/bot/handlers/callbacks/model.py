"""Model callbacks (mod:) — extracted from callbacks.py"""
from telegram.constants import ParseMode

from ....config import settings
from ....core.session_manager import session_manager


async def handle(query, context, chat_id: int, work_dir: str, payload: str) -> bool:
    from ....core.models import build_models_html, build_models_keyboard, find_preset_model
    mod_id = payload.strip()
    matched = find_preset_model(mod_id)
    if matched:
        new_model = matched["model"]
        settings.runtime_model = new_model
        session_manager.save_state()
        await query.answer(f"✅ Model diubah ke: {matched['name']}", show_alert=False)
        text = build_models_html(settings.runtime_model)
        kb = build_models_keyboard(settings.runtime_model)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        return True
    await query.answer("❌ Model tidak ditemukan.", show_alert=True)
    return True
