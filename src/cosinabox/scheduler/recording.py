"""Record every job execution, and derive what cadence a job expects.

`job_runs` and `analytics.get_job_health` both shipped without a writer, so
job counts and failure stats always reported zero. `wire_job_recording`
is that writer.

Recording is also the precondition for detecting a job that *never* fires:
existing alerting only triggers when a job runs and produces bad output,
and `heartbeat` proves the scheduler process is alive rather than that any
particular job executed. See `cosinabox.jobs.job_watchdog`.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from cosinabox.jobs.base import JobContext

logger = logging.getLogger(__name__)

# How many upcoming fire times to sample when inferring a job's cadence.
# Must be >= 6 so a Mon–Fri cron sees at least one Fri→Mon weekend gap.
_PERIOD_SAMPLES = 8


def expected_period(trigger: Any, *, now: datetime) -> timedelta | None:
    """The longest gap between consecutive fires of ``trigger``.

    Asks the trigger itself rather than parsing the cron string, so any
    trigger APScheduler understands works. The *longest* gap is the right
    measure: a Mon–Fri job idles three days over a weekend, and using an
    average would page every Sunday.

    Returns None for a trigger with no future fires (e.g. a date trigger
    already in the past), which callers treat as "cannot judge".
    """
    times: list[datetime] = []
    cursor = now
    previous: datetime | None = None
    for _ in range(_PERIOD_SAMPLES):
        try:
            nxt = trigger.get_next_fire_time(previous, cursor)
        except Exception:  # noqa: BLE001 — a trigger we cannot sample is not fatal
            logger.debug("Could not sample fire times for %r", trigger, exc_info=True)
            break
        if nxt is None:
            break
        times.append(nxt)
        previous = nxt
        cursor = nxt + timedelta(seconds=1)

    gaps = [b - a for a, b in zip(times, times[1:], strict=False)]
    return max(gaps) if gaps else None


def wire_job_recording(scheduler: Any, db: Any) -> None:
    """Wrap each registered job's ``run`` so every execution is recorded.

    Follows the same monkey-patch shape as ``wire_telegram_output``. Wrapping
    ``run`` rather than the scheduler's trigger callback means a manual
    ``run_now`` is recorded too — which is what you want, since a hand-run job
    is genuine evidence the job is alive.

    A recording failure is swallowed: observability must never take down the
    thing it observes. A failing *job* still records (status ``error``) and
    then re-raises, so the scheduler's own error handling is unchanged.
    """
    for jname, registered_job in scheduler._jobs.items():
        original = registered_job.run

        def _wrap(original: Any, name: str) -> Any:
            def wrapped(ctx: JobContext | None = None) -> str:
                started_at = datetime.now(UTC)
                clock = time.monotonic()
                status = "ok"
                result: str = ""
                try:
                    result = str(original(ctx or JobContext()) or "")
                    return result
                except Exception:
                    status = "error"
                    raise
                finally:
                    try:
                        db.record_job_run(
                            job_name=name,
                            started_at=started_at,
                            duration_ms=int((time.monotonic() - clock) * 1000),
                            status=status,
                            output_length=len(result or ""),
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("Could not record job run for %s", name)

            return wrapped

        registered_job.run = _wrap(original, jname)  # see wire_telegram_output
