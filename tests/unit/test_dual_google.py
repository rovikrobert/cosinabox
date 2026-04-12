"""Tests for dual-account Google support."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

# --- auth ---


def test_build_all_credentials_numbered_tokens() -> None:
    from cosinabox.tools.google.auth import build_all_credentials

    env = {
        "GOOGLE_OAUTH_CLIENT_ID": "cid",
        "GOOGLE_OAUTH_CLIENT_SECRET": "secret",
        "GOOGLE_OAUTH_REFRESH_TOKEN_1": "token1",
        "GOOGLE_OAUTH_REFRESH_TOKEN_2": "token2",
    }
    with patch.dict("os.environ", env, clear=False):
        creds = build_all_credentials()
    assert len(creds) == 2
    assert creds[0].refresh_token == "token1"
    assert creds[1].refresh_token == "token2"


def test_build_all_credentials_single_fallback() -> None:
    from cosinabox.tools.google.auth import build_all_credentials

    env = {
        "GOOGLE_OAUTH_CLIENT_ID": "cid",
        "GOOGLE_OAUTH_CLIENT_SECRET": "secret",
        "GOOGLE_OAUTH_REFRESH_TOKEN": "single-token",
    }
    # Remove numbered tokens if present
    import os

    with patch.dict("os.environ", env, clear=False):
        for k in ["GOOGLE_OAUTH_REFRESH_TOKEN_1", "GOOGLE_OAUTH_REFRESH_TOKEN_2"]:
            os.environ.pop(k, None)
        creds = build_all_credentials()
    assert len(creds) == 1
    assert creds[0].refresh_token == "single-token"


# --- gmail multi-service ---


def _fake_gmail_service(messages: list[dict]) -> MagicMock:
    svc = MagicMock()
    list_call = MagicMock()
    list_call.execute.return_value = {"messages": [{"id": m["id"]} for m in messages]}
    svc.users.return_value.messages.return_value.list.return_value = list_call
    by_id = {m["id"]: m for m in messages}

    def get_side_effect(userId, id, format):  # noqa: ARG001
        get_call = MagicMock()
        get_call.execute.return_value = by_id[id]
        return get_call

    svc.users.return_value.messages.return_value.get.side_effect = get_side_effect
    return svc


def test_gmail_merges_multiple_services() -> None:
    from cosinabox.tools.google.gmail import GmailTool

    msg_a = {"id": "m1", "snippet": "hello", "payload": {"headers": []}}
    msg_b = {"id": "m2", "snippet": "world", "payload": {"headers": []}}
    msg_dup = {"id": "m1", "snippet": "hello dup", "payload": {"headers": []}}

    svc1 = _fake_gmail_service([msg_a])
    svc2 = _fake_gmail_service([msg_b, msg_dup])

    tool = GmailTool(services=[svc1, svc2])
    msgs = tool.list_recent(hours=24)
    ids = [m.id for m in msgs]
    assert "m1" in ids
    assert "m2" in ids
    assert ids.count("m1") == 1  # deduplicated


# --- calendar multi-service ---


def _fake_calendar_service(events: list[dict]) -> MagicMock:
    svc = MagicMock()
    list_call = MagicMock()
    list_call.execute.return_value = {"items": events}
    svc.events.return_value.list.return_value = list_call
    return svc


def test_calendar_merges_multiple_services() -> None:
    from cosinabox.tools.google.calendar import CalendarTool

    now = datetime(2026, 4, 12, 9, 0, tzinfo=UTC)
    end = datetime(2026, 4, 12, 17, 0, tzinfo=UTC)

    evt_a = {
        "id": "e1",
        "summary": "Meeting A",
        "start": {"dateTime": "2026-04-12T10:00:00+00:00"},
        "end": {"dateTime": "2026-04-12T11:00:00+00:00"},
    }
    evt_b = {
        "id": "e2",
        "summary": "Meeting B",
        "start": {"dateTime": "2026-04-12T14:00:00+00:00"},
        "end": {"dateTime": "2026-04-12T15:00:00+00:00"},
    }
    evt_dup = {
        "id": "e1",
        "summary": "Meeting A dup",
        "start": {"dateTime": "2026-04-12T10:00:00+00:00"},
        "end": {"dateTime": "2026-04-12T11:00:00+00:00"},
    }

    svc1 = _fake_calendar_service([evt_a])
    svc2 = _fake_calendar_service([evt_b, evt_dup])

    tool = CalendarTool(services=[svc1, svc2])
    events = tool.list_events(start=now, end=end)
    ids = [e.id for e in events]
    assert "e1" in ids
    assert "e2" in ids
    assert ids.count("e1") == 1  # deduplicated
