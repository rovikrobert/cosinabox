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


def test_prompt_forbids_carry_over_when_no_db() -> None:
    """Without a commitments DB, the wrap must stay in sent-mail-only mode
    (PR #56 behavior) — no grounded source for open items, so CARRY-OVER /
    TOMORROW would hallucinate.
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
    assert "Do NOT produce CARRY-OVER" in prompt
    assert "Do not invent items" in prompt
    assert "memory" in prompt or "prior briefings" in prompt


def test_grounded_mode_restores_carry_over_and_uses_verified_rules(tmp_path) -> None:
    """With a commitments DB, CARRY-OVER + TOMORROW come back — but the
    cos-agent absolute rules ground them in the verifier output.
    """
    from cosinabox.commitments import create_commitment
    from cosinabox.memory import Memory

    db = Memory(db_path=tmp_path / "t.db")
    create_commitment(db, title="send NTU deck")

    gmail = MagicMock()
    # No subject matches the NTU deck keywords → stays GENUINELY OPEN.
    gmail.search.return_value = []

    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "ok"
    job = EveningWrapJob(
        gmail=gmail,
        agent_loop=fake_loop,
        personality="",
        name_for_briefing="Alex",
        db=db,
    )
    job.run(JobContext())

    prompt = fake_loop.run.call_args.kwargs["prompt"]
    assert "CARRY-OVER" in prompt
    assert "TOMORROW" in prompt
    assert "VERIFIED DONE" in prompt  # rules reference the verifier groups
    assert "GENUINELY OPEN" in prompt
    # The commitment verification section appears in the prefetch.
    assert "GENUINELY OPEN" in prompt
    assert "send NTU deck" in prompt
