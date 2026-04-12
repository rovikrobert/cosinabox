from __future__ import annotations

from unittest.mock import MagicMock

from cosinabox.jobs.base import JobContext
from cosinabox.jobs.evening_wrap import EveningWrapJob


def test_evening_wrap_runs() -> None:
    gmail = MagicMock()
    gmail.search.return_value = [
        MagicMock(sender="me", subject="Re: thing", snippet="..."),
    ]
    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "Today's wrap."
    job = EveningWrapJob(
        gmail=gmail,
        agent_loop=fake_loop,
        personality="brief",
        name_for_briefing="Alex",
    )
    out = job.run(JobContext())
    assert out == "Today's wrap."


def test_evening_wrap_skips_missing_gmail() -> None:
    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "No mail today."
    job = EveningWrapJob(
        gmail=None,
        agent_loop=fake_loop,
        personality="brief",
        name_for_briefing="Alex",
    )
    assert "No mail today." in job.run(JobContext())
