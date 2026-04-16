"""Synchronous Telegram bot adapter for the scheduling subsystem.

The scheduling outreach pipeline (``cosinabox.scheduling.outreach``) runs in
synchronous worker threads (poll check job, tool handlers). The python-
telegram-bot ``Application.bot`` object is async and uses a different
``send_poll`` signature (it sends an actual poll object, not an inline
keyboard), so wiring it directly would AttributeError/TypeError at runtime.

This adapter fulfils the sync scheduling bot contract documented in
``outreach.py``:

    bot.send_poll(
        *, chat_id, text, buttons: list[tuple[str, str]],
    ) -> dict  # {"message_id": int}

It does so by calling the Telegram HTTP Bot API directly (``sendMessage``)
with an ``inline_keyboard`` reply markup. One button per row — matches the
layout ``outreach.send_telegram_poll`` assembles.
"""

from __future__ import annotations

from typing import Any

import httpx


class SyncSchedulingBotAdapter:
    """Sync wrapper over Telegram's ``sendMessage`` HTTP endpoint."""

    def __init__(self, bot_token: str) -> None:
        self._bot_token = bot_token

    def send_poll(
        self,
        *,
        chat_id: int | str,
        text: str,
        buttons: list[tuple[str, str]],
    ) -> dict[str, Any]:
        """POST an inline-keyboard message to Telegram.

        ``buttons`` is a list of ``(label, callback_data)`` tuples, rendered
        one per row. Returns ``{"message_id": <int>}`` on success; raises
        ``RuntimeError`` on non-200 responses or ``ok: false`` payloads.
        """
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        inline_keyboard = [[{"text": label, "callback_data": data}] for label, data in buttons]
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": {"inline_keyboard": inline_keyboard},
        }
        resp = httpx.post(url, json=payload, timeout=15.0)
        if resp.status_code != 200:
            raise RuntimeError(f"Telegram sendMessage failed: HTTP {resp.status_code}")
        body = resp.json()
        if not body.get("ok"):
            raise RuntimeError(
                f"Telegram sendMessage returned ok=false: {body.get('description')!r}"
            )
        result = body.get("result") or {}
        return {"message_id": result.get("message_id")}


__all__ = ["SyncSchedulingBotAdapter"]
