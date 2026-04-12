from __future__ import annotations

from datetime import date, timedelta

from cosinabox.jobs.base import JobContext
from cosinabox.jobs.followup_reminder import FollowupReminderJob


def test_surfaces_stale_only() -> None:
    today = date(2026, 4, 12)
    stakeholders = [
        {"name": "Fresh", "cadence": "weekly", "last_contact": (today - timedelta(days=3)).isoformat()},
        {"name": "Stale", "cadence": "weekly", "last_contact": (today - timedelta(days=30)).isoformat()},
        {"name": "Monthly OK", "cadence": "monthly", "last_contact": (today - timedelta(days=20)).isoformat()},
    ]
    job = FollowupReminderJob(stakeholders=stakeholders, today=today)
    out = job.run(JobContext())
    assert "Stale" in out
    assert "Fresh" not in out
    assert "Monthly OK" not in out
