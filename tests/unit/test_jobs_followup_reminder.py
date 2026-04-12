from __future__ import annotations

from datetime import date, timedelta

from cosinabox.jobs.base import JobContext
from cosinabox.jobs.followup_reminder import FollowupReminderJob


def test_surfaces_stale_only() -> None:
    today = date(2026, 4, 12)
    fresh = (today - timedelta(days=3)).isoformat()
    stale = (today - timedelta(days=30)).isoformat()
    monthly_ok = (today - timedelta(days=20)).isoformat()
    stakeholders = [
        {"name": "Fresh", "cadence": "weekly", "last_contact": fresh},
        {"name": "Stale", "cadence": "weekly", "last_contact": stale},
        {"name": "Monthly OK", "cadence": "monthly", "last_contact": monthly_ok},
    ]
    job = FollowupReminderJob(stakeholders=stakeholders, today=today)
    out = job.run(JobContext())
    assert "Stale" in out
    assert "Fresh" not in out
    assert "Monthly OK" not in out
