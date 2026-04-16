"""Telegram bot adapter — single-account, DM + group modes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from telegram import Update
from telegram.ext import (
    Application,
    CallbackContext,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

ChatMode = str  # "dm" | "group"
MessageHandlerFn = Callable[[Update, ChatMode], Awaitable[None]]
CallbackHandlerFn = Callable[[Update, CallbackContext], Awaitable[None]]  # type: ignore[type-arg]  # telegram's CallbackContext has 4 type params; leaving default


class TelegramBot:
    def __init__(self, token: str) -> None:
        self.token = token
        self._handlers: list[MessageHandlerFn] = []
        self._callback_handlers: list[tuple[str, CallbackHandlerFn]] = []
        self._app: Application | None = None  # type: ignore[type-arg]

    def register_message_handler(self, handler: MessageHandlerFn) -> None:
        self._handlers.append(handler)

    def register_callback_handler(
        self,
        prefix: str,
        fn: CallbackHandlerFn,
    ) -> None:
        """Register an inline-button callback handler for callback_data matching ``prefix``.

        Prefixes are matched via ``startswith`` on ``update.callback_query.data``.
        Handlers are dispatched in registration order; the first matching prefix
        wins. If no prefix matches, the callback is silently ignored.
        """
        self._callback_handlers.append((prefix, fn))

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

    async def _on_callback(self, update: Update, ctx: CallbackContext) -> None:  # type: ignore[type-arg]
        query = getattr(update, "callback_query", None)
        if query is None:
            return
        data = getattr(query, "data", None) or ""
        for prefix, fn in self._callback_handlers:
            if data.startswith(prefix):
                await fn(update, ctx)
                return

    def start_polling(self) -> None:
        self._app = Application.builder().token(self.token).build()
        self._app.add_handler(MessageHandler(filters.ALL, self._on_message))
        self._app.add_handler(CallbackQueryHandler(self._on_callback))
        self._app.run_polling()
