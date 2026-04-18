"""Tests for ``wire_telegram_output`` — the wrapper that forwards a job's
``run()`` return string to Telegram.

Parallel to PR #51's persist-on-direct-send fix: any text the user sees on
Telegram from a wrapped job (pre-meeting prep, morning briefing, evening
wrap, weekly review, follow-up reminder, ...) must also land in the DM
session as ``role=assistant`` so DM follow-ups can recall the message.
"""

from __future__ import annotations

from typing import Any

import pytest
from cosinabox.app.alerts import wire_telegram_output
from cosinabox.jobs.base import Job, JobContext
from cosinabox.memory import Memory
from cosinabox.scheduler.runner import SchedulerRunner


class _ReturnTextJob(Job):
    """Minimal Job whose run() returns a fixed string (mirrors PreMeetingPrep,
    MorningBriefing, etc.)."""

    name = "return_text_job"

    def __init__(self, text: str) -> None:
        self._text = text

    def run(self, context: JobContext) -> str:
        return self._text


class _NoOpScheduler:
    """In-memory stand-in for the APScheduler backend; we only exercise the
    SchedulerRunner._jobs registry that wire_telegram_output walks."""

    def add_job(self, *args: Any, **kwargs: Any) -> None:
        pass


@pytest.fixture
def mem(tmp_path):
    return Memory(db_path=tmp_path / "wrap.db")


@pytest.fixture
def scheduler():
    return SchedulerRunner(scheduler=_NoOpScheduler())


def test_wrapper_persists_sent_text_to_dm_session(scheduler, mem):
    sent: list[str] = []
    job = _ReturnTextJob("Meeting: Project Sync at 10:00\nKey points: ship v1.")
    scheduler.add_job(job, cron="* * * * *")
    job.name = "pre_meeting_prep"  # the wrapper prefixes with [name]
    scheduler._jobs = {"pre_meeting_prep": job}

    wire_telegram_output(
        scheduler,
        sent.append,
        memory=mem,
        dm_session="dm-12345",
    )

    # Trigger the wrapped run.
    scheduler._jobs["pre_meeting_prep"].run(JobContext())

    assert sent, "send_fn should have been called"
    history = mem.recent_messages(session_id="dm-12345")
    assistant_msgs = [m for m in history if m["role"] == "assistant"]
    assert assistant_msgs, "wrapped job text should be persisted as assistant"
    joined = "\n".join(m["content"] for m in assistant_msgs)
    # The persisted text must include what the user actually saw on Telegram
    # (including the [job_name] header) so a DM follow-up can recall context.
    assert "pre_meeting_prep" in joined
    assert "Project Sync" in joined


def test_wrapper_skips_persist_when_dm_session_not_configured(scheduler, mem):
    """Backwards-compat: legacy app wiring without memory+dm_session must
    still send to Telegram and not error."""
    sent: list[str] = []
    job = _ReturnTextJob("morning briefing body")
    job.name = "morning_briefing"
    scheduler._jobs = {"morning_briefing": job}

    # No memory/dm_session passed.
    wire_telegram_output(scheduler, sent.append)

    scheduler._jobs["morning_briefing"].run(JobContext())

    assert sent, "send_fn should still be called when DM persist is off"
    assert mem.recent_messages(session_id="dm-anything") == []


def test_wrapper_does_not_persist_no_op_returns(scheduler, mem):
    """If the job returns a NO_OP marker (e.g. ``"no upcoming meetings"``)
    or empty string, the wrapper short-circuits and we must not write a
    misleading empty assistant message into DM history."""
    sent: list[str] = []
    job = _ReturnTextJob("no upcoming meetings")
    job.name = "pre_meeting_prep"
    scheduler._jobs = {"pre_meeting_prep": job}

    wire_telegram_output(
        scheduler,
        sent.append,
        memory=mem,
        dm_session="dm-12345",
    )

    scheduler._jobs["pre_meeting_prep"].run(JobContext())

    assert sent == [], "no-op result should not trigger send_fn"
    assert mem.recent_messages(session_id="dm-12345") == []
