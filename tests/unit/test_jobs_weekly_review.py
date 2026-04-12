from __future__ import annotations

from unittest.mock import MagicMock

from cosinabox.jobs.base import JobContext
from cosinabox.jobs.weekly_review import WeeklyReviewJob


def test_weekly_review_runs() -> None:
    gmail = MagicMock()
    gmail.search.return_value = []
    cal = MagicMock()
    cal.list_events.return_value = []
    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "Week recap."
    job = WeeklyReviewJob(
        gmail=gmail,
        calendar=cal,
        agent_loop=fake_loop,
        personality="reflective",
        name_for_briefing="Alex",
    )
    assert job.run(JobContext()) == "Week recap."
