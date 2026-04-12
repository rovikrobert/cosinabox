"""Telegram bot adapter — single-account, DM + group modes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from telegram import Update
from telegram.ext import Application, CallbackContext, MessageHandler, filters

ChatMode = str  # "dm" | "group"
MessageHandlerFn = Callable[[Update, ChatMode], Awaitable[None]]


class TelegramBot:
    def __init__(self, token: str) -> None:
        self.token = token
        self._handlers: list[MessageHandlerFn] = []
        self._app: Application | None = None  # type: ignore[type-arg]

    def register_message_handler(self, handler: MessageHandlerFn) -> None:
        self._handlers.append(handler)

    @staticmethod
    def classify(update: Update) -> ChatMode:
        if update.effective_chat is None:
            return "dm"
        return "dm" if update.effective_chat.type == "private" else "group"

    async def send(self, *, chat_id: int, text: str) -> None:
        assert self._app is not None, "bot not started; call start_polling first"
        await self._app.bot.send_message(chat_id=chat_id, text=text)

    async def _on_message(self, update: Update, _ctx: CallbackContext) -> None:  # type: ignore[type-arg]
        mode = self.classify(update)
        for handler in self._handlers:
            await handler(update, mode)

    def start_polling(self) -> None:
        self._app = Application.builder().token(self.token).build()
        self._app.add_handler(MessageHandler(filters.ALL, self._on_message))
        self._app.run_polling()
