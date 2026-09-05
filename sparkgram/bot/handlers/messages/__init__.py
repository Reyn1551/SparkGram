"""Messages package — 10/10 modularity. Re-exports for backward compat."""
from .utils import get_short_model_name, get_short_dir, get_current_time_str, build_response_keyboard, build_processing_keyboard
from .handler import message_handler, execute_prompt_task
from .stream_worker import stream_execution_worker, _stream_execution_worker

__all__ = [
    "message_handler",
    "execute_prompt_task",
    "stream_execution_worker",
    "_stream_execution_worker",
    "get_short_model_name",
    "get_short_dir",
    "get_current_time_str",
    "build_response_keyboard",
    "build_processing_keyboard",
]
