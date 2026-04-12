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
