from __future__ import annotations

from unittest.mock import MagicMock

from cosinabox.jobs.base import JobContext
from cosinabox.jobs.morning_briefing import MorningBriefingJob


def test_briefing_runs_against_stub_tools() -> None:
    gmail = MagicMock()
    gmail.list_recent.return_value = [
        MagicMock(sender="A", subject="X", snippet="..."),
    ]
    cal = MagicMock()
    cal.list_events.return_value = [
        MagicMock(summary="Standup", start=MagicMock(), end=MagicMock()),
    ]
    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "Your morning briefing."
    job = MorningBriefingJob(
        gmail=gmail,
        calendar=cal,
        agent_loop=fake_loop,
        personality="Be direct.",
        name_for_briefing="Alex",
    )
    text = job.run(JobContext())
    assert text == "Your morning briefing."
    fake_loop.run.assert_called_once()


def test_briefing_skips_missing_gmail() -> None:
    cal = MagicMock()
    cal.list_events.return_value = []
    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "No email today."
    job = MorningBriefingJob(
        gmail=None,
        calendar=cal,
        agent_loop=fake_loop,
        personality="Be direct.",
        name_for_briefing="Alex",
    )
    text = job.run(JobContext())
    assert "No email today." in text


def test_prefetch_uses_threads_needing_reply_not_unread() -> None:
    """Regression: briefing should no longer send `is:unread newer_than:24h`.

    That bucket catches things the user already replied to on another device,
    causing stale recommendations. The threads.list + SENT-label path is
    authoritative.
    """
    from cosinabox.tools.google.gmail import ThreadSummary

    gmail = MagicMock()
    gmail.list_recent.return_value = []
    gmail.list_threads_needing_reply.return_value = [
        ThreadSummary(
            thread_id="t1",
            subject="Re: NTU",
            last_sender="Adwin <adwin@ntu.edu.sg>",
            last_date="Fri, 18 Apr 2026 10:35 +0000",
            last_snippet="Any update?",
            last_sent_by_me=False,
        )
    ]
    cal = MagicMock()
    cal.list_events.return_value = []

    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "briefing"
    job = MorningBriefingJob(
        gmail=gmail,
        calendar=cal,
        agent_loop=fake_loop,
        personality="",
        name_for_briefing="Alex",
    )
    job.run(JobContext())

    gmail.list_threads_needing_reply.assert_called_once()
    # Belt-and-braces: we should not fall back to is:unread when the helper
    # returns data.
    for call in gmail.search.call_args_list:
        query = call.args[0] if call.args else call.kwargs.get("query", "")
        assert "is:unread" not in query

    prompt = fake_loop.run.call_args.kwargs["prompt"]
    assert "INBOX NEEDING REPLY" in prompt
    assert "ball" in prompt.lower()
    assert "Adwin" in prompt
    assert "Any update?" in prompt


def test_grounded_mode_uses_commitments_for_priorities(tmp_path) -> None:
    """With a commitments DB, PRIORITIES must come from GENUINELY OPEN —
    never from 'calendar + email signals'. That prevents zombie-item
    priorities.
    """
    from cosinabox.commitments import create_commitment
    from cosinabox.memory import Memory

    db = Memory(db_path=tmp_path / "t.db")
    create_commitment(db, title="close X deck", priority=1)

    gmail = MagicMock()
    gmail.list_recent.return_value = []
    gmail.list_threads_needing_reply.return_value = []
    gmail.search.return_value = []
    cal = MagicMock()
    cal.list_events.return_value = []

    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "ok"
    job = MorningBriefingJob(
        gmail=gmail,
        calendar=cal,
        agent_loop=fake_loop,
        personality="",
        name_for_briefing="Alex",
        db=db,
    )
    job.run(JobContext())

    prompt = fake_loop.run.call_args.kwargs["prompt"]
    assert "top 3 items from GENUINELY OPEN" in prompt
    assert "close X deck" in prompt
    assert "VERIFIED DONE" in prompt
    # No fallback text when db is present.
    assert "top 3 based on calendar + email signals" not in prompt
