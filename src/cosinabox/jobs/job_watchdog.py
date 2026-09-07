"""Dead-man's switch — alert on a job that stopped firing.

Every other health check in the engine answers "did this job run badly?".
None answers "did this job run at all?", and the scheduler heartbeat only
proves the *process* is alive. In the legacy implementation that gap
produced a 2026-06-15 → 07-20 outage: four weeks with no weekly digest, no
signals, and no alert of any kind, because the job simply never fired.

This job compares each registered job's last recorded run against the
cadence its own cron implies, and alerts on silence.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from cosinabox.jobs.base import Job, JobContext
from cosinabox.scheduler.recording import expected_period
from cosinabox.timezone import get_timezone

logger = logging.getLogger(__name__)

# A late run is drift; a missing run is an outage. Allow half a cycle before
# paging (so a daily job has 36h, a weekly job 10.5 days), with a floor so
# frequent jobs are not paged for one skipped tick.
_GRACE_FRACTION = 0.5
_GRACE_FLOOR = timedelta(minutes=15)


def _tolerance(period: timedelta) -> timedelta:
    return period + max(period * _GRACE_FRACTION, _GRACE_FLOOR)


class JobWatchdogJob(Job):
    name = "job_watchdog"

    def __init__(
        self,
        *,
        scheduler: Any,
        db: Any,
        alert_fn: Callable[[str], None],
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.scheduler = scheduler
        self.db = db
        self.alert_fn = alert_fn
        self.now_fn = now_fn or (lambda: datetime.now(UTC))

    def _period_for(self, cron: str, tz: str | None, now: datetime) -> timedelta | None:
        from apscheduler.triggers.cron import CronTrigger

        try:
            trigger = CronTrigger.from_crontab(cron, timezone=ZoneInfo(tz or get_timezone()))
        except Exception:  # noqa: BLE001 — a cron we cannot parse is not this job's failure
            logger.warning("Watchdog could not parse cron %r", cron, exc_info=True)
            return None
        return expected_period(trigger, now=now)

    def run(self, context: JobContext) -> str:
        now = self.now_fn()
        # first_job_run tells us how long recording has been in place. Without
        # it a fresh deployment would page for every job before its first
        # cycle, which trains you to ignore the alert.
        watching_since = self.db.first_job_run()

        checked = 0
        stale: list[str] = []

        for job_name, (cron, tz) in self.scheduler.schedules().items():
            if job_name == self.name:
                continue  # it records its own runs; watching itself is noise
            period = self._period_for(cron, tz, now)
            if period is None:
                continue
            checked += 1
            tolerance = _tolerance(period)
            last = self.db.last_job_run(job_name)

            if last is None:
                if watching_since is not None and now - watching_since > tolerance:
                    stale.append(
                        f"{job_name} has never run (cron '{cron}', expected every "
                        f"{_humanize(period)}); other jobs have been running for "
                        f"{_humanize(now - watching_since)}"
                    )
                continue

            overdue_by = now - last
            if overdue_by > tolerance:
                stale.append(
                    f"{job_name} last ran {_humanize(overdue_by)} ago "
                    f"(cron '{cron}', expected every {_humanize(period)})"
                )

        if stale:
            body = "Scheduled jobs that have gone quiet:\n" + "\n".join(
                f"- {line}" for line in stale
            )
            try:
                self.alert_fn(body)
            except Exception:  # noqa: BLE001 — a broken alert channel must not kill the check
                logger.exception("Watchdog could not send its alert")
            return body

        return f"Job watchdog: {checked} job(s) checked, all on schedule."


def _humanize(delta: timedelta) -> str:
    seconds = int(delta.total_seconds())
    if seconds < 90 * 60:
        return f"{max(seconds // 60, 1)}m"
    if seconds < 48 * 3600:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"
