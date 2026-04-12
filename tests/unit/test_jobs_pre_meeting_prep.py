from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from cosinabox.jobs.base import JobContext
from cosinabox.jobs.pre_meeting_prep import PreMeetingPrepJob


def _evt(summary: str, minutes_out: int):
    start = datetime.now(UTC) + timedelta(minutes=minutes_out)
    return MagicMock(id=summary, summary=summary, start=start, end=start + timedelta(minutes=30))


def test_fires_only_for_events_in_window() -> None:
    cal = MagicMock()
    cal.list_events.return_value = [
        _evt("Soon", 10),  # too soon
        _evt("Window", 30),  # in window (25-35)
        _evt("Later", 60),  # too far
    ]
    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "prep brief"
    job = PreMeetingPrepJob(
        calendar=cal,
        agent_loop=fake_loop,
        personality="brief",
        minutes_before=30,
        window_minutes=5,
        skip_titles=[],
    )
    msgs = job.run(JobContext())
    assert "Window" in msgs
    assert "Soon" not in msgs


def test_skip_titles_match() -> None:
    cal = MagicMock()
    cal.list_events.return_value = [
        _evt("Lunch", 30),
        _evt("Real Meeting", 30),
    ]
    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "prep"
    job = PreMeetingPrepJob(
        calendar=cal,
        agent_loop=fake_loop,
        personality="brief",
        minutes_before=30,
        window_minutes=5,
        skip_titles=["lunch"],
    )
    out = job.run(JobContext())
    assert "Real Meeting" in out
    assert "Lunch" not in out
