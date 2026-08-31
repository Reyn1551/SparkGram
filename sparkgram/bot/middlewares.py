"""
Middlewares and Access Control for SparkGram.
"""
import logging
from typing import Optional
from telegram import Update
from ..config import settings

log = logging.getLogger(__name__)


def is_allowed(update: Update) -> bool:
    """Checks if the effective user is authorized to interact with the bot."""
    if not settings.allowed_user_ids:
        # If allowed_user_ids is empty, allow all users (open mode)
        return True
    user = update.effective_user
    if not user:
        return False
    return user.id in settings.allowed_user_ids
