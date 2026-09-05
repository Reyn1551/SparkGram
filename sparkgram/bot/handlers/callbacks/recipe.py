"""Recipe callbacks (macro:) — extracted from callbacks.py"""

async def handle(query, context, chat_id: int, work_dir: str, payload: str, update=None) -> bool:
    payload = payload.strip()
    if payload.startswith("run:"):
        recipe_id = payload[4:]
        await query.answer(f"🚀 Menjalankan resep /{recipe_id}...")
        # update is the original Update that holds callback_query
        upd = update
        if upd is None:
            # fallback: try to get from context
            upd = getattr(context, 'update', None) or getattr(query, 'message', None)
        try:
            from ..recipe import _dispatch_macro
            # _dispatch_macro expects (update, context, recipe_id)
            target_update = upd if upd is not None else query  # type: ignore
            await _dispatch_macro(target_update, context, recipe_id)  # type: ignore
        except Exception:
            pass
        return True
    return False
