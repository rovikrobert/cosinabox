from __future__ import annotations

from unittest.mock import MagicMock

from cosinabox.tools.google.gmail import GmailTool


def _fake_service_with_messages(messages: list[dict]) -> MagicMock:
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


def test_get_recipients_parses_to_and_cc_headers() -> None:
    """get_recipients should return a flat list of email addresses from To + Cc."""
    svc = MagicMock()

    def get_side_effect(userId, id, format, metadataHeaders=None):  # noqa: ARG001
        get_call = MagicMock()
        get_call.execute.return_value = {
            "id": id,
            "payload": {
                "headers": [
                    {"name": "To", "value": "Alice <alice@example.com>, bob@example.com"},
                    {"name": "Cc", "value": "\"Carol Q.\" <carol@example.com>"},
                ],
            },
        }
        return get_call

    svc.users.return_value.messages.return_value.get.side_effect = get_side_effect
    tool = GmailTool(service=svc)
    recipients = tool.get_recipients("msg-1")
    assert "alice@example.com" in recipients
    assert "bob@example.com" in recipients
    assert "carol@example.com" in recipients
    assert len(recipients) == 3


def test_get_recipients_empty_when_headers_missing() -> None:
    svc = MagicMock()

    def get_side_effect(userId, id, format, metadataHeaders=None):  # noqa: ARG001
        get_call = MagicMock()
        get_call.execute.return_value = {"id": id, "payload": {"headers": []}}
        return get_call

    svc.users.return_value.messages.return_value.get.side_effect = get_side_effect
    tool = GmailTool(service=svc)
    assert tool.get_recipients("msg-1") == []


def test_get_recipients_returns_empty_on_api_error() -> None:
    """Best-effort: if API fails, return [] so the caller stays robust."""
    svc = MagicMock()
    get_call = MagicMock()
    get_call.execute.side_effect = Exception("API error")
    svc.users.return_value.messages.return_value.get.return_value = get_call
    tool = GmailTool(service=svc)
    assert tool.get_recipients("msg-1") == []


def test_list_recent_returns_parsed_messages() -> None:
    svc = _fake_service_with_messages(
        [
            {
                "id": "m1",
                "snippet": "hello",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Alice <a@x.com>"},
                        {"name": "Subject", "value": "Hi"},
                        {"name": "Date", "value": "Mon, 12 Apr 2026 09:00:00 +0000"},
                    ]
                },
            }
        ]
    )
    tool = GmailTool(service=svc)
    msgs = tool.list_recent(hours=24)
    assert len(msgs) == 1
    assert msgs[0].sender == "Alice <a@x.com>"
    assert msgs[0].subject == "Hi"
    assert msgs[0].snippet == "hello"
