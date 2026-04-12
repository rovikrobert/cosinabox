"""Scheduler runner — wraps APScheduler with cosinabox conventions."""

from __future__ import annotations

from typing import Any

from cosinabox.jobs.base import Job, JobContext


class SchedulerRunner:
    def __init__(self, *, scheduler: Any | None = None) -> None:
        if scheduler is None:
            from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]

            scheduler = BackgroundScheduler()
        self._scheduler = scheduler
        self._jobs: dict[str, Job] = {}

    def add_job(self, job: Job, *, cron: str) -> None:
        self._jobs[job.name] = job
        if hasattr(self._scheduler, "add_job"):
            from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]

            self._scheduler.add_job(
                lambda j=job: j.run(JobContext()),
                trigger=CronTrigger.from_crontab(cron),
                id=job.name,
                replace_existing=True,
            )

    def run_now(self, job_name: str, *, context: JobContext | None = None) -> str:
        job = self._jobs[job_name]
        return job.run(context or JobContext())

    def start(self) -> None:
        if hasattr(self._scheduler, "start"):
            self._scheduler.start()

    def shutdown(self) -> None:
        if hasattr(self._scheduler, "shutdown"):
            self._scheduler.shutdown()
