"""Followup reminder job — surfaces stale stakeholders.

Layer 1: followup_reminder default threshold = 14 days past cadence.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from cosinabox import defaults
from cosinabox.jobs.base import Job, JobContext

CADENCE_DAYS = {
    "daily": 1,
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
    "quarterly": 90,
}


class FollowupReminderJob(Job):
    name = "followup_reminder"

    def __init__(
        self,
        *,
        stakeholders: list[dict[str, Any]],
        today: date | None = None,
        staleness_days: int = defaults.FOLLOWUP_STALENESS_DAYS,
    ) -> None:
        self.stakeholders = stakeholders
        self.today = today or datetime.utcnow().date()
        self.staleness_days = staleness_days

    def run(self, context: JobContext) -> str:  # noqa: ARG002
        stale: list[str] = []
        for s in self.stakeholders:
            cadence = CADENCE_DAYS.get(s.get("cadence", "weekly"), 7)
            last = date.fromisoformat(s["last_contact"])
            days_since = (self.today - last).days
            if days_since > cadence + self.staleness_days:
                stale.append(f"- {s['name']} ({days_since}d since contact)")
        if not stale:
            return "(no stale follow-ups)"
        return "Stale follow-ups:\n" + "\n".join(stale)
