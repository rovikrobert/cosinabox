"""Rela daily scan — update relationship health scores for active stakeholders."""

from __future__ import annotations

import logging
from typing import Any

from cosinabox.jobs.base import Job

logger = logging.getLogger(__name__)

_ACTIVE_CADENCES = {"daily", "weekly", "biweekly"}


class RelaDailyScanJob(Job):
    name = "rela_daily_scan"

    def __init__(
        self,
        *,
        rela: Any | None,
        stakeholders: list[dict[str, Any]],
    ) -> None:
        self.rela = rela
        self.stakeholders = stakeholders

    def run(self, context: Any = None) -> str:
        if self.rela is None:
            return "Rela not configured — skipped"

        # Filter to active stakeholders
        active = [s for s in self.stakeholders if s.get("cadence", "").lower() in _ACTIVE_CADENCES]
        if not active:
            return "No active stakeholders — 0 scored"

        # Feed each stakeholder to Rela for scoring
        scored = 0
        for s in active:
            name = s.get("name", "")
            if not name:
                continue
            context_text = (
                f"Update relationship health for {name}.\n"
                f"Role: {s.get('role', 'unknown')}\n"
                f"Cadence: {s.get('cadence', 'unknown')}\n"
                f"Last contact: {s.get('last_contact', 'unknown')}\n"
                f"Use the calendar to check recent meetings and compute a health score."
            )
            try:
                self.rela.ingest(context_text)
                scored += 1
            except Exception:
                logger.warning("Rela scan failed for %s", name, exc_info=True)

        return f"Rela: scanned {scored} stakeholders"
