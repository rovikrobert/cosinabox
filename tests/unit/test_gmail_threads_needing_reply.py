# ruff: noqa: I001
"""Tests for `GmailTool.list_threads_needing_reply` — ball-in-court filter."""

from __future__ import annotations

from unittest.mock import MagicMock

from cosinabox.tools.google.gmail import GmailTool, ThreadSummary


# ---------------------------------------------------------------------------
# Fake Gmail service
# ---------------------------------------------------------------------------


def _stub_threads_list(ids: list[str]) -> dict:
    return {"threads": [{"id": i} for i in ids]}


def _make_msg(
    *,
    from_hdr: str,
    subject: str,
    date_hdr: str,
    snippet: str = "",
    sent: bool = False,
) -> dict:
    return {
        "labelIds": ["SENT"] if sent else ["INBOX", "UNREAD"],
        "snippet": snippet,
        "payload": {
            "headers": [
                {"name": "From", "value": from_hdr},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": date_hdr},
            ]
        },
    }


def _service_with_threads(threads: dict[str, dict]) -> MagicMock:
    """Build a MagicMock service where threads.get returns the given thread map.

    ``threads`` maps thread id → {"messages": [msg_dict, ...]}. ``messages`` are
    ordered oldest → newest (Gmail's default).
    """
    svc = MagicMock()
    svc.users.return_value.threads.return_value.list.return_value.execute.return_value = (
        _stub_threads_list(list(threads.keys()))
    )

    def _get(userId: str, id: str, **_: object):  # noqa: ARG001, N803
        inner = MagicMock()
        inner.execute.return_value = threads[id]
        return inner

    svc.users.return_value.threads.return_value.get.side_effect = _get
    return svc


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


def test_thread_with_last_message_from_them_needs_reply() -> None:
    svc = _service_with_threads(
        {
            "t1": {
                "messages": [
                    _make_msg(
                        from_hdr="Me <me@x.com>",
                        subject="Re: NTU",
                        date_hdr="Thu, 17 Apr 2026 22:35:00 +0000",
                        sent=True,
                    ),
                    _make_msg(
                        from_hdr="Adwin <adwin@ntu.edu.sg>",
                        subject="Re: NTU",
                        date_hdr="Fri, 18 Apr 2026 10:35:00 +0000",
                        snippet="Any update?",
                    ),
                ],
            }
        }
    )
    tool = GmailTool(service=svc)

    result = tool.list_threads_needing_reply(hours=24, max_results=10)

    assert len(result) == 1
    t = result[0]
    assert isinstance(t, ThreadSummary)
    assert t.thread_id == "t1"
    assert t.subject == "Re: NTU"
    assert "adwin" in t.last_sender.lower()
    assert t.last_sent_by_me is False


def test_thread_where_user_replied_last_is_excluded() -> None:
    svc = _service_with_threads(
        {
            "t1": {
                "messages": [
                    _make_msg(
                        from_hdr="Adwin <adwin@ntu.edu.sg>",
                        subject="NTU",
                        date_hdr="Thu, 17 Apr 2026 10:00:00 +0000",
                    ),
                    _make_msg(
                        from_hdr="Me <me@x.com>",
                        subject="Re: NTU",
                        date_hdr="Thu, 17 Apr 2026 22:35:00 +0000",
                        sent=True,
                    ),
                ],
            }
        }
    )
    tool = GmailTool(service=svc)

    assert tool.list_threads_needing_reply(hours=24, max_results=10) == []


def test_single_inbound_message_thread_needs_reply() -> None:
    svc = _service_with_threads(
        {
            "t1": {
                "messages": [
                    _make_msg(
                        from_hdr="New Person <new@x.com>",
                        subject="Intro",
                        date_hdr="Fri, 18 Apr 2026 06:00:00 +0000",
                        snippet="Wanted to reach out",
                    ),
                ],
            }
        }
    )
    tool = GmailTool(service=svc)

    result = tool.list_threads_needing_reply(hours=24, max_results=10)
    assert len(result) == 1
    assert result[0].last_sender == "New Person <new@x.com>"


def test_mixed_threads_filters_correctly() -> None:
    svc = _service_with_threads(
        {
            "waiting_on_me": {
                "messages": [
                    _make_msg(
                        from_hdr="X <x@x.com>",
                        subject="You're up",
                        date_hdr="Fri, 18 Apr 2026 08:00:00 +0000",
                    ),
                ],
            },
            "waiting_on_them": {
                "messages": [
                    _make_msg(
                        from_hdr="Y <y@y.com>",
                        subject="Ball in their court",
                        date_hdr="Thu, 17 Apr 2026 10:00:00 +0000",
                    ),
                    _make_msg(
                        from_hdr="Me <me@x.com>",
                        subject="Re: Ball in their court",
                        date_hdr="Fri, 18 Apr 2026 06:00:00 +0000",
                        sent=True,
                    ),
                ],
            },
        }
    )
    tool = GmailTool(service=svc)

    result = tool.list_threads_needing_reply(hours=24, max_results=10)
    assert [t.thread_id for t in result] == ["waiting_on_me"]


def test_empty_inbox_returns_empty_list() -> None:
    svc = _service_with_threads({})
    tool = GmailTool(service=svc)

    assert tool.list_threads_needing_reply(hours=24, max_results=10) == []


def test_query_excludes_promotions_and_social() -> None:
    """Regression: promotional/social emails should never populate the bucket."""
    svc = _service_with_threads({})
    tool = GmailTool(service=svc)

    tool.list_threads_needing_reply(hours=24, max_results=10)

    call_kwargs = svc.users.return_value.threads.return_value.list.call_args.kwargs
    query = call_kwargs["q"]
    assert "in:inbox" in query
    assert "-category:promotions" in query
    assert "-category:social" in query
    assert "newer_than:24h" in query
