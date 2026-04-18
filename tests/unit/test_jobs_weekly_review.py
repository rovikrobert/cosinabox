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


def test_prompt_forbids_misses_and_next_week_sections() -> None:
    """Regression: prior prompt asked for MISSES + NEXT WEEK sections which
    had no grounded prefetch source. Model confabulated from memory, same
    zombie-item bug class as evening_wrap.

    Until commitments + auto_resolve port from cos-agent, weekly review must
    stay within SENT MAIL + CALENDAR + STAKEHOLDER HEALTH.
    """
    gmail = MagicMock()
    gmail.search.return_value = []
    cal = MagicMock()
    cal.list_events.return_value = []
    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "ok"
    job = WeeklyReviewJob(
        gmail=gmail,
        calendar=cal,
        agent_loop=fake_loop,
        personality="",
        name_for_briefing="Alex",
    )
    job.run(JobContext())

    prompt = fake_loop.run.call_args.kwargs["prompt"]
    assert "Do NOT generate MISSES or NEXT WEEK" in prompt
    assert "Do not invent items" in prompt
