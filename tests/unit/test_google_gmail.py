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
