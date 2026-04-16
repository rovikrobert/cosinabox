"""Tests for SyncSchedulingBotAdapter — sync HTTP wrapper around Telegram sendMessage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cosinabox.bot.sync_scheduling_adapter import SyncSchedulingBotAdapter


def _fake_response(ok: bool = True, status_code: int = 200, message_id: int = 42):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = (
        {"ok": True, "result": {"message_id": message_id}}
        if ok
        else {"ok": False, "description": "Bad Request"}
    )
    return resp


def test_send_poll_posts_correct_url_and_payload():
    adapter = SyncSchedulingBotAdapter(bot_token="TEST_TOKEN")
    buttons = [("A", "cb:a"), ("B", "cb:b")]

    with patch("cosinabox.bot.sync_scheduling_adapter.httpx.post") as post:
        post.return_value = _fake_response(message_id=42)
        result = adapter.send_poll(
            chat_id=12345, text="pick a slot", buttons=buttons,
        )

    assert result == {"message_id": 42}
    assert post.call_count == 1
    args, kwargs = post.call_args
    url = args[0] if args else kwargs.get("url")
    assert url == "https://api.telegram.org/botTEST_TOKEN/sendMessage"

    body = kwargs.get("json")
    assert body is not None
    assert body["chat_id"] == 12345
    assert body["text"] == "pick a slot"
    # One button per row.
    assert body["reply_markup"] == {
        "inline_keyboard": [
            [{"text": "A", "callback_data": "cb:a"}],
            [{"text": "B", "callback_data": "cb:b"}],
        ]
    }


def test_send_poll_raises_on_non_200():
    adapter = SyncSchedulingBotAdapter(bot_token="TEST_TOKEN")

    with patch("cosinabox.bot.sync_scheduling_adapter.httpx.post") as post:
        post.return_value = _fake_response(ok=False, status_code=400)
        with pytest.raises(RuntimeError):
            adapter.send_poll(chat_id=1, text="x", buttons=[("A", "cb:a")])


def test_send_poll_empty_buttons_has_empty_keyboard():
    adapter = SyncSchedulingBotAdapter(bot_token="TOK")
    with patch("cosinabox.bot.sync_scheduling_adapter.httpx.post") as post:
        post.return_value = _fake_response(message_id=7)
        adapter.send_poll(chat_id=1, text="t", buttons=[])
    body = post.call_args.kwargs["json"]
    assert body["reply_markup"] == {"inline_keyboard": []}
