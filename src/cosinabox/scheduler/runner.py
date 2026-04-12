"""Scheduler runner — wraps APScheduler with cosinabox conventions."""
# mypy: disable-error-code="import-untyped"

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from cosinabox.jobs.base import Job, JobContext
from cosinabox.timezone import get_timezone


class SchedulerRunner:
    def __init__(self, *, scheduler: Any | None = None) -> None:
        if scheduler is None:
            from apscheduler.schedulers.background import BackgroundScheduler

            scheduler = BackgroundScheduler(timezone=get_timezone())
        self._scheduler = scheduler
        self._jobs: dict[str, Job] = {}

    def add_job(self, job: Job, *, cron: str) -> None:
        self._jobs[job.name] = job
        if hasattr(self._scheduler, "add_job"):
            from apscheduler.triggers.cron import CronTrigger

            self._scheduler.add_job(
                lambda j=job: j.run(JobContext()),
                trigger=CronTrigger.from_crontab(cron),
                id=job.name,
                replace_existing=True,
            )

    def reschedule_all(self, new_tz: str) -> int:
        """Reschedule all CronTrigger jobs to a new timezone.

        Returns the count of rescheduled jobs.
        """
        from apscheduler.triggers.cron import CronTrigger

        count = 0
        tz_info = ZoneInfo(new_tz)
        for sched_job in self._scheduler.get_jobs():
            trigger = sched_job.trigger
            if not isinstance(trigger, CronTrigger):
                continue
            fields = {}
            for field_name in (
                "year",
                "month",
                "day",
                "week",
                "day_of_week",
                "hour",
                "minute",
                "second",
            ):
                field = getattr(trigger, field_name, None)
                if field is not None:
                    fields[field_name] = str(field)
            new_trigger = CronTrigger(timezone=tz_info, **fields)
            sched_job.reschedule(trigger=new_trigger)
            count += 1
        return count

    def run_now(self, job_name: str, *, context: JobContext | None = None) -> str:
        job = self._jobs[job_name]
        return job.run(context or JobContext())

    def start(self) -> None:
        if hasattr(self._scheduler, "start"):
            self._scheduler.start()

    def shutdown(self) -> None:
        if hasattr(self._scheduler, "shutdown"):
            self._scheduler.shutdown()
