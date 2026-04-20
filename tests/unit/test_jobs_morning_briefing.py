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


def test_keep_warm_section_rendered_from_attio_overdue() -> None:
    """When Attio returns overdue Keep Warm people, prefetch + prompt include them."""
    from cosinabox.tools.attio import KeepWarmPerson

    gmail = MagicMock()
    gmail.list_recent.return_value = []
    gmail.list_threads_needing_reply.return_value = []
    cal = MagicMock()
    cal.list_events.return_value = []

    attio = MagicMock()
    attio.get_keep_warm_overdue.return_value = [
        KeepWarmPerson(
            name="Sarah Chen",
            record_id="r1",
            cadence_days=30,
            note="Lead Investor",
            last_interaction="2026-03-01T00:00:00Z",
            days_since=45,
        ),
        KeepWarmPerson(
            name="Tom Vasquez",
            record_id="r2",
            cadence_days=14,
            note=None,
            last_interaction="2026-03-22T00:00:00Z",
            days_since=29,
        ),
    ]

    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "ok"
    job = MorningBriefingJob(
        gmail=gmail,
        calendar=cal,
        agent_loop=fake_loop,
        personality="",
        name_for_briefing="Alex",
        attio=attio,
    )
    job.run(JobContext())

    prompt = fake_loop.run.call_args.kwargs["prompt"]
    assert "KEEP WARM — OVERDUE" in prompt
    assert "Sarah Chen" in prompt
    assert "Tom Vasquez" in prompt
    assert "45d since last contact" in prompt
    assert "cadence: 30d" in prompt
    # Note surfaces when present, absent when not.
    assert "Lead Investor" in prompt
    # Prompt adds the section 5 instruction.
    assert "5. KEEP WARM" in prompt


def test_keep_warm_omitted_when_no_overdue() -> None:
    """Attio returns an empty overdue list → KEEP WARM section quietly skipped."""
    gmail = MagicMock()
    gmail.list_recent.return_value = []
    gmail.list_threads_needing_reply.return_value = []
    cal = MagicMock()
    cal.list_events.return_value = []

    attio = MagicMock()
    attio.get_keep_warm_overdue.return_value = []

    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "ok"
    job = MorningBriefingJob(
        gmail=gmail,
        calendar=cal,
        agent_loop=fake_loop,
        personality="",
        name_for_briefing="Alex",
        attio=attio,
    )
    job.run(JobContext())

    prompt = fake_loop.run.call_args.kwargs["prompt"]
    # Section 5 instruction may still be in the prompt but the data block
    # does not contain a KEEP WARM section header.
    assert "KEEP WARM — OVERDUE:\n-" not in prompt


def test_keep_warm_section_skipped_when_attio_none() -> None:
    """No attio plumbed → no API call, no section, briefing still works."""
    gmail = MagicMock()
    gmail.list_recent.return_value = []
    gmail.list_threads_needing_reply.return_value = []
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
        # attio omitted → None default
    )
    job.run(JobContext())

    prompt = fake_loop.run.call_args.kwargs["prompt"]
    assert "KEEP WARM — OVERDUE" not in prompt
