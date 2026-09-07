# ruff: noqa: I001
"""A job that never fires must be detectable.

Existing alerting only fires when a job *runs* and produces bad output.
`heartbeat` proves the scheduler process is alive, not that any particular
job executed. In the legacy implementation that gap produced a
2026-06-15 → 07-20 outage: four weeks with no weekly digest, no signals,
and no alert of any kind.

Two halves, both here:

1. **Recording.** The `job_runs` table has existed since the SQLite
   schema was written and `analytics.get_job_health` reads it, but nothing
   ever wrote to it — so job counts and per-job failure stats always
   reported zero.
2. **Detection.** A watchdog that derives each job's expected cadence from
   its own cron trigger and alerts when the last recorded run is older
   than that plus a grace margin.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apscheduler.triggers.cron import CronTrigger

from cosinabox.jobs.base import Job, JobContext
from cosinabox.memory.sqlite import Memory
from cosinabox.scheduler.recording import expected_period, wire_job_recording
from cosinabox.scheduler.runner import SchedulerRunner
from cosinabox.jobs.job_watchdog import JobWatchdogJob


@pytest.fixture
def db(tmp_path):
    return Memory(db_path=tmp_path / "t.db")


class _Ok(Job):
    name = "ok_job"

    def __init__(self):
        self.calls = 0

    def run(self, context: JobContext) -> str:
        self.calls += 1
        return "did the thing"


class _Boom(Job):
    name = "boom_job"

    def run(self, context: JobContext) -> str:
        raise RuntimeError("kaboom")


# ── Recording ────────────────────────────────────────────────────────────


class TestRecording:
    def test_record_and_read_back_last_run(self, db):
        started = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
        db.record_job_run(
            job_name="morning_briefing",
            started_at=started,
            duration_ms=1234,
            status="ok",
            output_length=42,
        )
        assert db.last_job_run("morning_briefing") == started

    def test_last_run_is_none_for_a_job_that_never_ran(self, db):
        assert db.last_job_run("never_ran") is None

    def test_last_run_returns_the_most_recent(self, db):
        for day in (1, 5, 3):
            db.record_job_run(
                job_name="j",
                started_at=datetime(2026, 9, day, 8, 0, tzinfo=UTC),
                duration_ms=1,
                status="ok",
                output_length=0,
            )
        assert db.last_job_run("j").day == 5

    def test_recorded_runs_reach_analytics(self, db):
        """get_job_health has always reported 0 because nothing wrote rows."""
        from cosinabox.agent.analytics import get_job_health

        db.record_job_run(
            job_name="j",
            started_at=datetime.now(UTC),
            duration_ms=5,
            status="ok",
            output_length=1,
        )
        db.record_job_run(
            job_name="j",
            started_at=datetime.now(UTC),
            duration_ms=5,
            status="error",
            output_length=0,
        )
        health = get_job_health(db, days=7)
        assert health["runs_today"] == 2
        assert health["failing_jobs"] == [{"name": "j", "failures": 1}]

    def test_wiring_records_a_successful_run(self, db):
        scheduler = SchedulerRunner(scheduler=object())
        job = _Ok()
        scheduler.add_job(job, cron="0 8 * * *")
        wire_job_recording(scheduler, db)

        scheduler.run_now("ok_job")

        assert job.calls == 1
        assert db.last_job_run("ok_job") is not None

    def test_wiring_records_a_failure_and_still_raises(self, db):
        scheduler = SchedulerRunner(scheduler=object())
        scheduler.add_job(_Boom(), cron="0 8 * * *")
        wire_job_recording(scheduler, db)

        with pytest.raises(RuntimeError, match="kaboom"):
            scheduler.run_now("boom_job")

        # A crashed job still ran — the watchdog must not also cry "never fired".
        assert db.last_job_run("boom_job") is not None
        from cosinabox.agent.analytics import get_job_health

        assert get_job_health(db)["failing_jobs"] == [{"name": "boom_job", "failures": 1}]

    def test_a_recording_failure_never_breaks_the_job(self, db):
        """Observability must not take down the thing it observes."""

        class _BrokenDb:
            def record_job_run(self, **kwargs):
                raise sqlite_error()

        def sqlite_error():
            return RuntimeError("db gone")

        scheduler = SchedulerRunner(scheduler=object())
        job = _Ok()
        scheduler.add_job(job, cron="0 8 * * *")
        wire_job_recording(scheduler, _BrokenDb())

        assert scheduler.run_now("ok_job") == "did the thing"
        assert job.calls == 1


# ── Expected cadence, derived from the trigger itself ────────────────────


class TestExpectedPeriod:
    def test_daily_cron(self):
        now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
        period = expected_period(CronTrigger.from_crontab("0 8 * * *", timezone=UTC), now=now)
        assert period == timedelta(days=1)

    def test_every_fifteen_minutes(self):
        now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
        period = expected_period(CronTrigger.from_crontab("*/15 * * * *", timezone=UTC), now=now)
        assert period == timedelta(minutes=15)

    def test_weekly_cron(self):
        now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
        period = expected_period(CronTrigger.from_crontab("30 8 * * 1", timezone=UTC), now=now)
        assert period == timedelta(days=7)

    def test_weekday_cron_uses_the_largest_gap(self):
        """Fri -> Mon is 3 days. Sampling one interval would under-count and
        page every weekend."""
        now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
        period = expected_period(CronTrigger.from_crontab("0 9 * * 1-5", timezone=UTC), now=now)
        assert period == timedelta(days=3)


# ── Detection ────────────────────────────────────────────────────────────


def _scheduler_with(cron: str, name: str = "daily_job") -> SchedulerRunner:
    class _J(Job):
        def run(self, context: JobContext) -> str:
            return "ok"

    _J.name = name  # type: ignore[misc]
    s = SchedulerRunner(scheduler=object())
    s.add_job(_J(), cron=cron)
    return s


class TestWatchdog:
    def _run(self, db, scheduler, *, now):
        alerts: list[str] = []
        job = JobWatchdogJob(scheduler=scheduler, db=db, alert_fn=alerts.append, now_fn=lambda: now)
        summary = job.run(JobContext())
        return alerts, summary

    def test_a_job_that_ran_on_time_is_silent(self, db):
        now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
        db.record_job_run(
            job_name="daily_job",
            started_at=now - timedelta(hours=4),
            duration_ms=1,
            status="ok",
            output_length=1,
        )
        alerts, _ = self._run(db, _scheduler_with("0 8 * * *"), now=now)
        assert alerts == []

    def test_an_overdue_job_alerts_and_names_it(self, db):
        now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
        db.record_job_run(
            job_name="daily_job",
            started_at=now - timedelta(days=30),
            duration_ms=1,
            status="ok",
            output_length=1,
        )
        alerts, _ = self._run(db, _scheduler_with("0 8 * * *"), now=now)
        assert len(alerts) == 1
        assert "daily_job" in alerts[0]

    def test_the_four_week_outage_would_have_alerted(self, db):
        """The 2026-06-15 -> 07-20 shape: a weekly job, silent for a month."""
        now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
        db.record_job_run(
            job_name="asia_lab_tracker",
            started_at=datetime(2026, 6, 15, 8, 30, tzinfo=UTC),
            duration_ms=1,
            status="ok",
            output_length=1,
        )
        alerts, _ = self._run(db, _scheduler_with("30 8 * * 1", name="asia_lab_tracker"), now=now)
        assert len(alerts) == 1
        assert "asia_lab_tracker" in alerts[0]

    def test_grace_margin_tolerates_a_slightly_late_run(self, db):
        """A daily job 25h late is drift, not death — don't page for it."""
        now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
        db.record_job_run(
            job_name="daily_job",
            started_at=now - timedelta(hours=25),
            duration_ms=1,
            status="ok",
            output_length=1,
        )
        alerts, _ = self._run(db, _scheduler_with("0 8 * * *"), now=now)
        assert alerts == []

    def test_a_fresh_deployment_does_not_page_for_never_run_jobs(self, db):
        """No history at all means we have not been watching long enough."""
        now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
        alerts, _ = self._run(db, _scheduler_with("0 8 * * *"), now=now)
        assert alerts == []

    def test_a_job_that_never_ran_on_a_long_lived_system_alerts(self, db):
        """Other jobs have been running for days; this one has never fired.

        That is the misregistration case — and it is invisible to any check
        that only looks at jobs which have run.
        """
        now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
        db.record_job_run(
            job_name="some_other_job",
            started_at=now - timedelta(days=10),
            duration_ms=1,
            status="ok",
            output_length=1,
        )
        alerts, _ = self._run(db, _scheduler_with("0 8 * * *"), now=now)
        assert len(alerts) == 1
        assert "never" in alerts[0].lower()

    def test_summary_reports_when_all_jobs_are_healthy(self, db):
        now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
        db.record_job_run(
            job_name="daily_job",
            started_at=now - timedelta(hours=1),
            duration_ms=1,
            status="ok",
            output_length=1,
        )
        _, summary = self._run(db, _scheduler_with("0 8 * * *"), now=now)
        assert "1" in summary

    def test_an_alert_failure_does_not_break_the_watchdog(self, db):
        now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
        db.record_job_run(
            job_name="daily_job",
            started_at=now - timedelta(days=30),
            duration_ms=1,
            status="ok",
            output_length=1,
        )

        def boom(_msg):
            raise RuntimeError("telegram down")

        job = JobWatchdogJob(
            scheduler=_scheduler_with("0 8 * * *"),
            db=db,
            alert_fn=boom,
            now_fn=lambda: now,
        )
        job.run(JobContext())  # must not raise

    def test_the_watchdog_does_not_watch_itself(self, db):
        """It records its own run, so it would always look healthy — but
        listing it adds noise and invites a self-referential alert."""
        now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
        db.record_job_run(
            job_name="other",
            started_at=now - timedelta(days=10),
            duration_ms=1,
            status="ok",
            output_length=1,
        )
        scheduler = _scheduler_with("0 * * * *", name=JobWatchdogJob.name)
        alerts, _ = self._run(db, scheduler, now=now)
        assert alerts == []


class TestRegistration:
    """The watchdog only helps if it is actually registered and recording.

    An unregistered watchdog is indistinguishable from no watchdog, and the
    same is true of recording: a job registered after `wire_job_recording`
    runs unrecorded and then looks to the watchdog like a job that never
    fires. These assert the wiring, not just the logic.
    """

    def test_register_watchdog_registers_the_job(self, db):
        from cosinabox.app.jobs import register_watchdog

        scheduler = _scheduler_with("0 8 * * *")
        register_watchdog(scheduler, {}, send_telegram=lambda _m: None, memory=db)

        assert JobWatchdogJob.name in scheduler._jobs

    def test_register_watchdog_is_on_by_default(self, db):
        """A jobs.yaml predating this feature must still get outage detection."""
        from cosinabox.app.jobs import register_watchdog

        scheduler = _scheduler_with("0 8 * * *")
        register_watchdog(
            scheduler,
            {"morning_briefing": {"enabled": True}},
            send_telegram=lambda _m: None,
            memory=db,
        )
        assert JobWatchdogJob.name in scheduler._jobs

    def test_registration_wires_recording_for_existing_jobs(self, db):
        from cosinabox.app.jobs import register_watchdog

        scheduler = _scheduler_with("0 8 * * *")
        register_watchdog(scheduler, {}, send_telegram=lambda _m: None, memory=db)

        scheduler.run_now("daily_job")
        assert db.last_job_run("daily_job") is not None

    def test_disabling_the_watchdog_still_records_runs(self, db):
        """Recording feeds /analytics too, so it is not the watchdog's to opt out of."""
        from cosinabox.app.jobs import register_watchdog

        scheduler = _scheduler_with("0 8 * * *")
        register_watchdog(
            scheduler,
            {"job_watchdog": {"enabled": False}},
            send_telegram=lambda _m: None,
            memory=db,
        )

        assert JobWatchdogJob.name not in scheduler._jobs
        scheduler.run_now("daily_job")
        assert db.last_job_run("daily_job") is not None

    def test_the_registered_watchdog_alerts_through_telegram(self, db):
        from cosinabox.app.jobs import register_watchdog

        sent: list[str] = []
        scheduler = _scheduler_with("0 8 * * *")
        register_watchdog(scheduler, {}, send_telegram=sent.append, memory=db)

        db.record_job_run(
            job_name="daily_job",
            started_at=datetime.now(UTC) - timedelta(days=30),
            duration_ms=1,
            status="ok",
            output_length=1,
        )
        scheduler.run_now(JobWatchdogJob.name)

        assert any("daily_job" in m for m in sent), sent
