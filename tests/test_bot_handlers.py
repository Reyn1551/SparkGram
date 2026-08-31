"""
Unit Tests for Telegram Bot Handlers with Mock Objects.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, User, Chat, Message, CallbackQuery

from sparkgram.config import settings
from sparkgram.bot.middlewares import is_allowed
from sparkgram.bot.handlers.commands import (
    start_cmd,
    id_cmd,
    pwd_cmd,
    model_cmd,
    workdir_cmd,
    health_cmd,
    logs_cmd,
)
from sparkgram.bot.handlers.callbacks import callback_query_handler


def create_mock_update(user_id: int = 1925430810, chat_id: int = 1925430810, text: str = "/start") -> Update:
    user = User(id=user_id, first_name="TestUser", is_bot=False)
    chat = Chat(id=chat_id, type="private")
    message = MagicMock(spec=Message)
    message.reply_text = AsyncMock()
    message.delete = AsyncMock()
    message.edit_message_text = AsyncMock()
    message.text = text
    message.from_user = user
    message.chat = chat

    update = MagicMock(spec=Update)
    update.effective_user = user
    update.effective_chat = chat
    update.effective_message = message
    update.message = message
    return update


@pytest.mark.asyncio
async def test_is_allowed_middleware():
    settings.allowed_user_ids = {100, 200}
    up_allowed = create_mock_update(user_id=100)
    up_denied = create_mock_update(user_id=999)

    assert is_allowed(up_allowed) is True
    assert is_allowed(up_denied) is False


@pytest.mark.asyncio
async def test_start_cmd_allowed():
    settings.allowed_user_ids = {100}
    update = create_mock_update(user_id=100)
    context = MagicMock()

    await start_cmd(update, context)
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "SparkGram AI Bridge Aktif" in call_args


@pytest.mark.asyncio
async def test_id_cmd():
    settings.allowed_user_ids = {100}
    update = create_mock_update(user_id=100, chat_id=555)
    context = MagicMock()

    await id_cmd(update, context)
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "555" in call_args
    assert "100" in call_args


@pytest.mark.asyncio
async def test_health_cmd():
    settings.allowed_user_ids = {100}
    update = create_mock_update(user_id=100)
    context = MagicMock()

    await health_cmd(update, context)
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "Status Kesehatan Host & Companion PC" in call_args
    assert "RAM" in call_args
    assert "CPU" in call_args


@pytest.mark.asyncio
async def test_logs_cmd():
    settings.allowed_user_ids = {100}
    update = create_mock_update(user_id=100)
    context = MagicMock()
    context.args = ["10"]

    await logs_cmd(update, context)
    update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_model_cmd_interactive_list():
    settings.allowed_user_ids = {100}
    update = create_mock_update(user_id=100)
    context = MagicMock()
    context.args = []

    await model_cmd(update, context)
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "Pilih Model AI (1-Tap Switch)" in call_args
    assert "Muse Spark 1.2" in call_args


@pytest.mark.asyncio
async def test_model_cmd_quick_number_1():
    settings.allowed_user_ids = {100}
    update = create_mock_update(user_id=100)
    context = MagicMock()
    context.args = ["1"]

    await model_cmd(update, context)
    assert settings.runtime_model == "opencode/muse-spark-1.2-contributor-free"
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "Muse Spark 1.2" in call_args


@pytest.mark.asyncio
async def test_model_cmd_alias_spark():
    settings.allowed_user_ids = {100}
    update = create_mock_update(user_id=100)
    context = MagicMock()
    context.args = ["spark"]

    await model_cmd(update, context)
    assert settings.runtime_model == "opencode/muse-spark-1.2-contributor-free"
    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "Muse Spark 1.2" in call_args


@pytest.mark.asyncio
async def test_callback_query_model_switch():
    settings.allowed_user_ids = {100}
    user = User(id=100, first_name="TestUser", is_bot=False)
    chat = Chat(id=100, type="private")

    query = MagicMock(spec=CallbackQuery)
    query.data = "mod:1"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.callback_query = query
    update.effective_user = user
    update.effective_chat = chat
    context = MagicMock()

    await callback_query_handler(update, context)
    assert settings.runtime_model == "opencode/muse-spark-1.2-contributor-free"
    query.answer.assert_called_once()
    query.edit_message_text.assert_called_once()


@pytest.mark.asyncio
async def test_callback_query_health_refresh():
    settings.allowed_user_ids = {100}
    user = User(id=100, first_name="TestUser", is_bot=False)
    chat = Chat(id=100, type="private")

    query = MagicMock(spec=CallbackQuery)
    query.data = "hlth:refresh"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.callback_query = query
    update.effective_user = user
    update.effective_chat = chat
    context = MagicMock()

    await callback_query_handler(update, context)
    query.answer.assert_called_once()
    query.edit_message_text.assert_called_once()


@pytest.mark.asyncio
async def test_callback_query_logs_send_message():
    settings.allowed_user_ids = {100}
    user = User(id=100, first_name="TestUser", is_bot=False)
    chat = Chat(id=100, type="private")

    query = MagicMock(spec=CallbackQuery)
    query.data = "hlth:logs"
    query.answer = AsyncMock()

    update = MagicMock(spec=Update)
    update.callback_query = query
    update.effective_user = user
    update.effective_chat = chat
    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await callback_query_handler(update, context)
    query.answer.assert_called_once()
    context.bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_callback_query_workdir():
    settings.allowed_user_ids = {100}
    user = User(id=100, first_name="TestUser", is_bot=False)
    chat = Chat(id=100, type="private")

    query = MagicMock(spec=CallbackQuery)
    query.data = "sw:workdir"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.callback_query = query
    update.effective_user = user
    update.effective_chat = chat
    context = MagicMock()

    await callback_query_handler(update, context)
    query.answer.assert_called_once()
    query.edit_message_text.assert_called_once()


@pytest.mark.asyncio
async def test_callback_query_close():
    settings.allowed_user_ids = {100}
    user = User(id=100, first_name="TestUser", is_bot=False)
    chat = Chat(id=100, type="private")

    mock_msg = MagicMock(spec=Message)
    mock_msg.delete = AsyncMock()

    query = MagicMock(spec=CallbackQuery)
    query.data = "act:close"
    query.message = mock_msg
    query.answer = AsyncMock()

    update = MagicMock(spec=Update)
    update.callback_query = query
    update.effective_user = user
    update.effective_chat = chat
    context = MagicMock()

    await callback_query_handler(update, context)
    query.answer.assert_called_once()
    mock_msg.delete.assert_called_once()
