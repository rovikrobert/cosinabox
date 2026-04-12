from __future__ import annotations

from unittest.mock import MagicMock

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
