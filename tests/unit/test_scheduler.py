from __future__ import annotations

from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from apscheduler.triggers.cron import CronTrigger

from cosinabox import timezone as tz_mod
from cosinabox.jobs.base import Job, JobContext
from cosinabox.scheduler.runner import SchedulerRunner


class _StubJob(Job):
    name = "stub"

    def __init__(self) -> None:
        self.calls = 0

    def run(self, context: JobContext) -> str:
        self.calls += 1
        return "ran"


def test_scheduler_adds_and_runs_job_immediately(monkeypatch) -> None:
    runner = SchedulerRunner(scheduler=MagicMock())
    job = _StubJob()
    runner.add_job(job, cron="0 8 * * *")
    runner.run_now(job.name, context=JobContext(session_id="test"))
    assert job.calls == 1


def test_each_run_uses_unique_session_id() -> None:
    runner = SchedulerRunner(scheduler=MagicMock())
    seen: set[str] = set()

    class CaptureJob(Job):
        name = "capture"

        def run(self, ctx: JobContext) -> str:
            seen.add(ctx.session_id)
            return ""

    job = CaptureJob()
    runner.add_job(job, cron="0 8 * * *")
    runner.run_now(job.name)
    runner.run_now(job.name)
    assert len(seen) == 2


def test_add_job_trigger_uses_configured_timezone(monkeypatch) -> None:
    """Cron triggers must fire in the user's configured timezone, not OS-local.

    Without this, deployments in UTC containers (Railway) silently shift every
    cron-scheduled job by the user's UTC offset. Uses Asia/Tokyo so the test
    fails on hosts whose local TZ happens to match the engine default.
    """
    monkeypatch.setattr(tz_mod, "_timezone", "Asia/Tokyo")
    sched = MagicMock()
    runner = SchedulerRunner(scheduler=sched)
    runner.add_job(_StubJob(), cron="0 8 * * *")

    trigger = sched.add_job.call_args.kwargs["trigger"]
    assert isinstance(trigger, CronTrigger)
    assert trigger.timezone == ZoneInfo("Asia/Tokyo")


def test_add_job_per_job_timezone_overrides_default(monkeypatch) -> None:
    """jobs.yaml's per-job `timezone:` field must reach the cron trigger."""
    monkeypatch.setattr(tz_mod, "_timezone", "Asia/Singapore")
    sched = MagicMock()
    runner = SchedulerRunner(scheduler=sched)
    runner.add_job(_StubJob(), cron="0 8 * * *", timezone="America/New_York")

    trigger = sched.add_job.call_args.kwargs["trigger"]
    assert trigger.timezone == ZoneInfo("America/New_York")
