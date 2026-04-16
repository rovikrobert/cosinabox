"""Follow-up reminder — surfaces stale stakeholder contacts."""

from __future__ import annotations

from datetime import date
from typing import Any

from cosinabox import defaults
from cosinabox.jobs.base import Job, JobContext


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
        self.today = today or date.today()
        self.staleness_days = staleness_days

    def run(self, context: JobContext) -> str:
        cadence_map = {
            "daily": 1,
            "weekly": 7,
            "biweekly": 14,
            "monthly": 30,
            "quarterly": 90,
        }
        stale: list[str] = []
        for s in self.stakeholders:
            lc = s.get("last_contact") or s.get("last_interaction")
            if not lc:
                continue
            try:
                last = date.fromisoformat(str(lc)[:10])
            except (ValueError, TypeError):
                continue
            days = (self.today - last).days
            cadence = s.get("cadence", "weekly")
            threshold = cadence_map.get(cadence, 7) + self.staleness_days
            if days > threshold:
                name = s.get("name", "?")
                role = s.get("role", "")
                stale.append(f"- {name} ({role}) — {days}d since last contact, cadence: {cadence}")

        if not stale:
            return ""  # Empty = no message sent

        return f"Follow-up reminder ({len(stale)} contacts cooling):\n\n" + "\n".join(stale)
