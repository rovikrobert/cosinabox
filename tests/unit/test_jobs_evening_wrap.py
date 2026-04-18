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


def test_prompt_forbids_carry_over_and_tomorrow_sections() -> None:
    """Regression: earlier prompts asked for CARRY-OVER / TOMORROW sections,
    which Claude confabulated from conversation memory when the prefetch only
    had sent mail. The rovik-keevs 2026-04-18 wrap surfaced zombie items
    ("Recruiter shortlist", "SOW with Daniel") days after they were resolved.

    Until cosinabox ports the commitments + auto_resolve subsystem, evening
    wrap must stay grounded in sent mail only.
    """
    gmail = MagicMock()
    gmail.search.return_value = []
    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "ok"
    job = EveningWrapJob(
        gmail=gmail,
        agent_loop=fake_loop,
        personality="",
        name_for_briefing="Alex",
    )
    job.run(JobContext())

    prompt = fake_loop.run.call_args.kwargs["prompt"]
    # The prompt must not instruct the model to generate these sections.
    assert "Do NOT produce CARRY-OVER" in prompt
    # Explicit anti-hallucination rule is present.
    assert "Do not invent items" in prompt
    assert "memory" in prompt or "prior briefings" in prompt
