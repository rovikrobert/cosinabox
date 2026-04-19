"""Follow-up reminder — surfaces stale stakeholder contacts.

Uses two signals for "last contact":

1. ``last_contact`` / ``last_interaction`` in ``stakeholders.yaml``. Manual,
   may be months stale because nothing auto-updates it.
2. If the stakeholder has an ``email`` field AND a Gmail tool is plumbed in,
   the freshest sent-mail date to that email in the last 90 days.

The freshest of the two wins. Without this, users got nagged about people
they'd emailed yesterday because the yaml file hadn't caught up.
"""

from __future__ import annotations

import logging
from datetime import date
from email.utils import parsedate_to_datetime
from typing import Any

from cosinabox import defaults
from cosinabox.jobs.base import Job, JobContext

logger = logging.getLogger(__name__)


def _parse_message_date(raw: str) -> date | None:
    """Parse the Gmail RFC 2822 Date header. Returns None if unparseable."""
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).date()
    except (TypeError, ValueError):
        return None


class FollowupReminderJob(Job):
    name = "followup_reminder"

    def __init__(
        self,
        *,
        stakeholders: list[dict[str, Any]],
        gmail: Any | None = None,
        today: date | None = None,
        staleness_days: int = defaults.FOLLOWUP_STALENESS_DAYS,
    ) -> None:
        self.stakeholders = stakeholders
        self.gmail = gmail
        self.today = today or date.today()
        self.staleness_days = staleness_days

    def _last_sent_mail_date(self, email: str) -> date | None:
        """Return the date of the most recent sent mail to ``email``.

        Returns None if Gmail isn't configured, the search fails, or nothing
        was sent to that address in the 90-day lookback window.
        """
        if self.gmail is None or not email:
            return None
        query = f"in:sent to:{email} newer_than:90d"
        try:
            messages = self.gmail.search(query, max_results=5)
        except Exception:
            logger.debug("gmail search failed for %s", email, exc_info=True)
            return None

        best: date | None = None
        for msg in messages:
            raw = getattr(msg, "date", "") or ""
            parsed = _parse_message_date(raw)
            if parsed is None:
                continue
            if best is None or parsed > best:
                best = parsed
        return best

    def run(self, context: JobContext | None = None) -> str:
        cadence_map = {
            "daily": 1,
            "weekly": 7,
            "biweekly": 14,
            "monthly": 30,
            "quarterly": 90,
        }
        stale: list[str] = []
        for s in self.stakeholders:
            yaml_date: date | None = None
            lc = s.get("last_contact") or s.get("last_interaction")
            if lc:
                try:
                    yaml_date = date.fromisoformat(str(lc)[:10])
                except (ValueError, TypeError):
                    yaml_date = None

            gmail_date: date | None = None
            email = s.get("email")
            if email:
                gmail_date = self._last_sent_mail_date(str(email))

            candidates = [d for d in (yaml_date, gmail_date) if d is not None]
            if not candidates:
                continue
            last = max(candidates)

            days = (self.today - last).days
            cadence = s.get("cadence", "weekly")
            threshold = cadence_map.get(cadence, 7) + self.staleness_days
            if days > threshold:
                name = s.get("name", "?")
                role = s.get("role", "")
                stale.append(f"- {name} ({role}) — {days}d since last contact, cadence: {cadence}")

        if not stale:
            return ""

        return f"Follow-up reminder ({len(stale)} contacts cooling):\n\n" + "\n".join(stale)
