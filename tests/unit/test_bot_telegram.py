from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cosinabox.bot.telegram import TelegramBot


@pytest.fixture
def bot() -> TelegramBot:
    return TelegramBot(token="fake-token")


async def test_send_calls_telegram_api(bot: TelegramBot, monkeypatch) -> None:
    fake_app = MagicMock()
    fake_app.bot.send_message = AsyncMock()
    monkeypatch.setattr(bot, "_app", fake_app)
    await bot.send(chat_id=12345, text="hello")
    fake_app.bot.send_message.assert_awaited_once_with(chat_id=12345, text="hello")


async def test_classify_chat_dm_vs_group(bot: TelegramBot) -> None:
    dm_update = MagicMock()
    dm_update.effective_chat.type = "private"
    group_update = MagicMock()
    group_update.effective_chat.type = "supergroup"
    assert bot.classify(dm_update) == "dm"
    assert bot.classify(group_update) == "group"


async def test_register_handler_records_callback(bot: TelegramBot) -> None:
    cb = AsyncMock()
    bot.register_message_handler(cb)
    assert cb in bot._handlers
