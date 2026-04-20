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


def test_prompt_forbids_misses_and_next_week_when_no_db() -> None:
    """No db → stay in PR #56 mode: drop MISSES + NEXT WEEK entirely."""
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


def test_grounded_mode_restores_misses_and_next_week(tmp_path) -> None:
    """With a commitments DB, MISSES + NEXT WEEK return with verifier rules."""
    from cosinabox.commitments import create_commitment
    from cosinabox.memory import Memory

    db = Memory(db_path=tmp_path / "t.db")
    create_commitment(db, title="ship NTU deck Q3")

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
        db=db,
    )
    job.run(JobContext())

    prompt = fake_loop.run.call_args.kwargs["prompt"]
    assert "MISSES" in prompt
    assert "NEXT WEEK" in prompt
    assert "VERIFIED DONE" in prompt
    assert "GENUINELY OPEN" in prompt
    assert "ship NTU deck Q3" in prompt
