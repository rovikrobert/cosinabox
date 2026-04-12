from __future__ import annotations

from unittest.mock import MagicMock, patch

from cosinabox.tools.google.auth import build_all_credentials
from cosinabox.tools.google.calendar import CalendarTool
from cosinabox.tools.google.gmail import GmailTool


def test_build_all_credentials_numbered_tokens() -> None:
    env = {
        "GOOGLE_OAUTH_CLIENT_ID": "cid",
        "GOOGLE_OAUTH_CLIENT_SECRET": "sec",
        "GOOGLE_OAUTH_REFRESH_TOKEN_1": "tok1",
        "GOOGLE_OAUTH_REFRESH_TOKEN_2": "tok2",
    }
    with patch.dict("os.environ", env, clear=True):
        creds = build_all_credentials()
    assert len(creds) == 2


def test_build_all_credentials_single_fallback() -> None:
    env = {
        "GOOGLE_OAUTH_CLIENT_ID": "cid",
        "GOOGLE_OAUTH_CLIENT_SECRET": "sec",
        "GOOGLE_OAUTH_REFRESH_TOKEN": "tok",
    }
    with patch.dict("os.environ", env, clear=True):
        creds = build_all_credentials()
    assert len(creds) == 1


def test_gmail_merges_two_accounts() -> None:
    svc1 = MagicMock()
    svc1.users().messages().list().execute.return_value = {"messages": [{"id": "msg1"}]}
    svc1.users().messages().get().execute.return_value = {
        "id": "msg1",
        "payload": {"headers": [{"name": "Subject", "value": "From acct 1"}]},
    }
    svc2 = MagicMock()
    svc2.users().messages().list().execute.return_value = {"messages": [{"id": "msg2"}]}
    svc2.users().messages().get().execute.return_value = {
        "id": "msg2",
        "payload": {"headers": [{"name": "Subject", "value": "From acct 2"}]},
    }
    tool = GmailTool(services=[svc1, svc2])
    results = tool.list_recent(max_results=10)
    ids = [r.id for r in results]
    assert "msg1" in ids
    assert "msg2" in ids


def test_calendar_merges_two_accounts() -> None:
    svc1 = MagicMock()
    svc1.events().list().execute.return_value = {
        "items": [
            {
                "id": "evt1",
                "summary": "Meeting 1",
                "start": {"dateTime": "2026-04-12T10:00:00+08:00"},
                "end": {"dateTime": "2026-04-12T11:00:00+08:00"},
            }
        ]
    }
    svc2 = MagicMock()
    svc2.events().list().execute.return_value = {
        "items": [
            {
                "id": "evt2",
                "summary": "Meeting 2",
                "start": {"dateTime": "2026-04-12T14:00:00+08:00"},
                "end": {"dateTime": "2026-04-12T15:00:00+08:00"},
            }
        ]
    }
    tool = CalendarTool(services=[svc1, svc2])
    from datetime import datetime

    events = tool.list_events(
        start=datetime.fromisoformat("2026-04-12T00:00:00+08:00"),
        end=datetime.fromisoformat("2026-04-12T23:59:00+08:00"),
    )
    ids = [e.id for e in events]
    assert "evt1" in ids
    assert "evt2" in ids
