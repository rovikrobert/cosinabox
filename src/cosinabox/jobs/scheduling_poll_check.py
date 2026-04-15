"""Scheduling poll check — 30-min cron that advances POLLING requests.

For each POLLING scheduling request:
  1. Fetch Gmail replies via ``coordinator.check_polling_status`` — that
     function parses and records any new responses.
  2. If ``find_consensus`` returns a slot, transition POLLING → CONVERGED
     and notify the owner via ``send_fn``.
  3. Otherwise, for each participant that still has not responded, compute
     the age of their outreach:
       - >= 24h since outreach_sent_at and status == 'sent' → nudge
         (status becomes 'nudged'; no dedicated nudged_at column exists —
         the status flip guards against re-nudging).
       - >= 48h since outreach_sent_at → expire (status 'no_response').
  4. If ALL non-responded participants have expired, transition POLLING →
     OWNER_REVIEW and notify the owner.

Returns a summary string: e.g.
    "checked 3 requests, 1 converged, 2 nudged, 1 expired"
    or "skipped — no active polls"

Notes for OSS users:
- ``send_fn(text)`` is a single callable; this job does not know about
  Telegram chat IDs. App wiring chooses where messages land.
- Nudge messages are plain text sent via ``send_fn``. Sending a Telegram
  DM directly to the participant is an app-level concern (Phase B).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from cosinabox.jobs.base import Job
from cosinabox.scheduling import db as sched_db
from cosinabox.scheduling.coordinator import (
    InvalidTransition,
    check_polling_status,
    find_consensus,
    transition,
)
from cosinabox.scheduling.models import SchedulingStatus

logger = logging.getLogger(__name__)


_NUDGE_HOURS = 24
_EXPIRE_HOURS = 48
# Safety cap: if the bot was down through the nudge window, we still want to
# nudge once before expiring — but not after 3 days (too stale to be useful).
_NUDGE_SAFETY_CAP_HOURS = 72


class SchedulingPollCheckJob(Job):
    name = "scheduling_poll_check"

    def __init__(
        self,
        *,
        db: Any,
        anthropic_client: Any,
        send_fn: Callable[[str], None],
        gmail: Any | None = None,
        cost_tracker: Any | None = None,
    ) -> None:
        self.db = db
        self.gmail = gmail
        self.anthropic_client = anthropic_client
        self.cost_tracker = cost_tracker
        self.send_fn = send_fn

    def run(self, context: Any = None) -> str:
        active = sched_db.get_active_requests(
            self.db, status_filter=[SchedulingStatus.POLLING.value],
        )
        if not active:
            return "skipped — no active polls"

        now = datetime.now(UTC)
        converged = 0
        nudged_total = 0
        expired_total = 0
        owner_review_total = 0

        for req in active:
            # 1. Poll Gmail / parse responses.
            try:
                check_polling_status(
                    self.db,
                    req.id,
                    gmail=self.gmail,
                    anthropic_client=self.anthropic_client,
                    cost_tracker=self.cost_tracker,
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "check_polling_status failed for %s", req.id,
                )

            # 2. Consensus?
            consensus = find_consensus(self.db, req.id)
            if consensus is not None:
                try:
                    transition(
                        self.db, req.id,
                        SchedulingStatus.POLLING, SchedulingStatus.CONVERGED,
                    )
                    converged += 1
                    local_start = consensus.start_time
                    self.send_fn(
                        f"Scheduling: consensus reached for '{req.title}' — "
                        f"slot {local_start.isoformat()}. "
                        "Use the book action to confirm."
                    )
                except InvalidTransition:
                    logger.warning(
                        "Could not transition %s to converged", req.id,
                    )
                continue

            # 3. Nudge / expire participants by outreach age.
            nudged_names: list[str] = []
            expired_names: list[str] = []
            remaining_active = 0

            # Re-load participants (status may have flipped to 'responded'
            # inside check_polling_status).
            fresh_participants = sched_db.get_participants(self.db, req.id)
            for p in fresh_participants:
                if p.status in ("responded", "no_response"):
                    continue
                if p.db_id is None:
                    continue

                sent_at = sched_db.get_participant_outreach_sent_at(
                    self.db, p.db_id,
                )
                if sent_at is None:
                    # Outreach never sent (or draft-only Gmail). Skip.
                    remaining_active += 1
                    continue

                # Normalise timezone for comparison.
                if sent_at.tzinfo is None:
                    sent_at = sent_at.replace(tzinfo=UTC)

                age_hours = (now - sent_at).total_seconds() / 3600.0

                # Nudge-before-expire guard: if we're past the expire window
                # but never nudged (e.g. bot was down 24-48h window), send the
                # nudge first and defer expire to the next cycle — but only if
                # we're still within the safety cap (72h). Past the cap, expire
                # without nudging (the nudge would be too stale to matter).
                in_expire_window = age_hours >= _EXPIRE_HOURS
                in_nudge_window = age_hours >= _NUDGE_HOURS
                can_still_nudge = age_hours < _NUDGE_SAFETY_CAP_HOURS

                if in_expire_window and p.status == "sent" and can_still_nudge:
                    # Bot-down-during-nudge-window recovery path.
                    self.send_fn(
                        f"Scheduling nudge: {p.name} hasn't responded to "
                        f"'{req.title}' in {int(age_hours)}h. "
                        "Consider reaching out directly."
                    )
                    sched_db.update_participant_status(
                        self.db, p.db_id, "nudged",
                    )
                    nudged_names.append(p.name)
                    remaining_active += 1
                elif in_expire_window:
                    # Either already nudged, or past safety cap — expire.
                    sched_db.update_participant_status(
                        self.db, p.db_id, "no_response",
                    )
                    expired_names.append(p.name)
                elif in_nudge_window and p.status == "sent":
                    self.send_fn(
                        f"Scheduling nudge: {p.name} hasn't responded to "
                        f"'{req.title}' in {int(age_hours)}h. "
                        "Consider reaching out directly."
                    )
                    sched_db.update_participant_status(
                        self.db, p.db_id, "nudged",
                    )
                    nudged_names.append(p.name)
                    remaining_active += 1
                else:
                    remaining_active += 1

            nudged_total += len(nudged_names)
            expired_total += len(expired_names)

            # 4. All non-responded participants expired → owner review.
            if expired_names and remaining_active == 0:
                # Are there any participants still in 'responded'?
                # Escalate regardless — owner should decide next step.
                try:
                    transition(
                        self.db, req.id,
                        SchedulingStatus.POLLING,
                        SchedulingStatus.OWNER_REVIEW,
                    )
                    owner_review_total += 1
                    self.send_fn(
                        f"Scheduling: '{req.title}' returned for review — "
                        f"expired without response: {', '.join(expired_names)}. "
                        "Book with partial responses, extend, or cancel."
                    )
                except InvalidTransition:
                    logger.warning(
                        "Could not transition %s to owner_review", req.id,
                    )

        parts = [
            f"checked {len(active)} request(s)",
            f"{converged} converged",
            f"{nudged_total} nudged",
            f"{expired_total} expired",
        ]
        if owner_review_total:
            parts.append(f"{owner_review_total} to owner review")
        return ", ".join(parts)


__all__ = ["SchedulingPollCheckJob"]
