"""
DEPRECATED shim - use `python -m sparkgram` or `python bot_bridge_live.py`.
Kept for backward compatibility only. Delegates to sparkgram.main.run_bot().
Original legacy preserved at scripts/legacy/bot_bridge_legacy.py
"""
import warnings
warnings.warn("bot_bridge.py is deprecated, use `python -m sparkgram` or `python bot_bridge_live.py`", DeprecationWarning, stacklevel=2)

from sparkgram.main import run_bot

if __name__ == "__main__":
    print("[DEPRECATED] bot_bridge.py -> delegating to sparkgram.main.run_bot(). Use `python -m sparkgram` next time.")
    run_bot()
