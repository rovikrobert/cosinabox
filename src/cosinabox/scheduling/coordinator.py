"""Scheduling coordinator — state machine for group meeting coordination.

Ported from cos-agent/src/scheduling/coordinator.py, converted async→sync and
generalised for OSS: owner name / timezone are parameters, no hardcoded
"Rovik"/"SGT". Calendar-event booking is deferred to Phase B (Plan 5) — the
``book`` action only transitions the state, it does not create a calendar
event.

State flow (see _TRANSITIONS below):

    PROPOSING ──► OWNER_REVIEW ──► POLLING ──► CONVERGED ──► BOOKED
         │            │ ▲            │ │            │
         │            │ └────────────┘ │            │
         │            ▼                ▼            │
         └──► BACKCHANNEL     EXPIRED / CANCELLED ──┘

Only seven edges are legal; everything else raises ``InvalidTransition``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from cosinabox.scheduling import db as sched_db
from cosinabox.scheduling.models import (
    Participant,
    SchedulingRequest,
    SchedulingStatus,
    TimeSlot,
)
from cosinabox.scheduling.outreach import execute_outreach
from cosinabox.scheduling.response_parser import parse_response
from cosinabox.scheduling.slot_scorer import (
    ScoringConfig,
    compute_score,
    events_to_busy_intervals,
    find_candidate_slots,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

# Exactly 7 legal edges. Terminal states (BOOKED, CANCELLED, EXPIRED) have
# no outgoing edges.
_TRANSITIONS: dict[SchedulingStatus, set[SchedulingStatus]] = {
    SchedulingStatus.PROPOSING: {
        SchedulingStatus.OWNER_REVIEW,
        SchedulingStatus.BACKCHANNEL,
        SchedulingStatus.CANCELLED,
    },
    SchedulingStatus.OWNER_REVIEW: {
        SchedulingStatus.POLLING,
        SchedulingStatus.PROPOSING,
        SchedulingStatus.CANCELLED,
    },
    SchedulingStatus.POLLING: {
        SchedulingStatus.CONVERGED,
        SchedulingStatus.OWNER_REVIEW,
        SchedulingStatus.EXPIRED,
        SchedulingStatus.CANCELLED,
    },
    SchedulingStatus.BACKCHANNEL: {
        SchedulingStatus.PROPOSING,
        SchedulingStatus.OWNER_REVIEW,
        SchedulingStatus.CANCELLED,
    },
    SchedulingStatus.CONVERGED: {
        SchedulingStatus.BOOKED,
        SchedulingStatus.CANCELLED,
    },
    SchedulingStatus.BOOKED: set(),
    SchedulingStatus.CANCELLED: set(),
    SchedulingStatus.EXPIRED: set(),
}


class InvalidTransition(Exception):
    """Raised when an illegal state transition is attempted."""


def _coerce(status: SchedulingStatus | str) -> SchedulingStatus:
    if isinstance(status, SchedulingStatus):
        return status
    return SchedulingStatus(status)


def transition(
    db: Any,
    request_id: str,
    from_status: SchedulingStatus | str,
    to_status: SchedulingStatus | str,
) -> None:
    """Validate and execute a status transition, persisting to DB.

    Raises ``InvalidTransition`` if the edge is not in ``_TRANSITIONS``.
    Does not inspect the DB's current status — the caller is responsible
    for passing the correct ``from_status``.
    """
    frm = _coerce(from_status)
    to = _coerce(to_status)
    allowed = _TRANSITIONS.get(frm, set())
    if to not in allowed:
        raise InvalidTransition(
            f"Cannot transition from {frm.value!r} to {to.value!r}. "
            f"Legal targets: "
            f"{sorted(s.value for s in allowed) if allowed else 'none (terminal)'}"
        )
    # Optimistic concurrency: UPDATE ... WHERE status=? so concurrent
    # transitions from the same source state don't both "win".
    ok = sched_db.update_request_status_guarded(db, request_id, frm.value, to.value)
    if not ok:
        raise InvalidTransition(f"Concurrent transition — status is no longer {frm.value!r}")


# ---------------------------------------------------------------------------
# start_scheduling — create a request, compute slots, surface for review.
# ---------------------------------------------------------------------------


def start_scheduling(
    *,
    db: Any,
    participants: list[Participant],
    duration_minutes: int,
    date_range_start: date,
    date_range_end: date,
    owner_events: dict[date, list[dict[str, Any]]] | None = None,
    owner_timezone: str,
    owner_name: str,
    title: str | None = None,
    notes: str | None = None,
    scoring_config: ScoringConfig | None = None,
    anthropic_client: Any | None = None,  # noqa: ARG001 - reserved, unused here
    cost_tracker: Any | None = None,  # noqa: ARG001 - reserved, unused here
) -> SchedulingRequest:
    """Create a scheduling request, score candidate slots, surface for owner review.

    Transitions:
        (new) → PROPOSING → OWNER_REVIEW, or → CANCELLED if no viable slots.

    Returns the hydrated ``SchedulingRequest`` (with slots attached). The
    caller (tool handler) is responsible for formatting the user-facing
    message from the returned request.
    """
    req = SchedulingRequest(
        id=uuid.uuid4().hex,
        title=title or f"{duration_minutes}-min meeting",
        duration_minutes=duration_minutes,
        participants=list(participants),
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        status=SchedulingStatus.PROPOSING.value,
        preferred_timezone=owner_timezone,
        notes=notes,
    )

    req_id = sched_db.create_request(db, req, requested_by=owner_name)

    slots = find_candidate_slots(
        participants=participants,
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        duration_minutes=duration_minutes,
        owner_events_by_day=owner_events or {},
        owner_timezone=owner_timezone,
        config=scoring_config,
    )

    if not slots:
        transition(db, req_id, SchedulingStatus.PROPOSING, SchedulingStatus.CANCELLED)
        logger.info(
            "start_scheduling: no viable slots for %s (%s..%s); cancelled",
            req_id,
            date_range_start,
            date_range_end,
        )
        hydrated = sched_db.get_request(db, req_id)
        return hydrated or req

    for slot in slots:
        sched_db.add_slot(db, req_id, slot)

    transition(
        db,
        req_id,
        SchedulingStatus.PROPOSING,
        SchedulingStatus.OWNER_REVIEW,
    )

    hydrated = sched_db.get_request(db, req_id)
    if hydrated is None:  # pragma: no cover - create just succeeded
        return req
    return hydrated


# ---------------------------------------------------------------------------
# Polling — check inbound Gmail replies, parse, record responses.
# ---------------------------------------------------------------------------


def _fetch_owner_events_for_slots(
    calendar: Any | None,
    req: SchedulingRequest,
) -> dict[date, list[dict[str, Any]]] | None:
    """Best-effort fetch of owner calendar events covering the request's
    slot dates. Returns ``None`` if no calendar adapter was supplied or the
    fetch fails — callers treat ``None`` as "skip fresh re-score".

    Adapter contract: ``calendar.list_events(start=datetime, end=datetime)``
    returns objects with ``.start`` / ``.end`` attributes (CalendarEvent).
    We re-shape them into the ``dict`` format ``find_consensus`` expects.
    """
    if calendar is None or not req.slots:
        return None
    list_events = getattr(calendar, "list_events", None)
    if not callable(list_events):
        return None
    # Compute day window from slot range.
    slot_dates = sorted({s.start_time.date() for s in req.slots})
    if not slot_dates:
        return None
    # Fetch one range covering all slot days.
    try:
        from zoneinfo import ZoneInfo

        utc = ZoneInfo("UTC")
        start = datetime.combine(slot_dates[0], datetime.min.time(), tzinfo=utc)
        end = datetime.combine(
            slot_dates[-1],
            datetime.min.time(),
            tzinfo=utc,
        ) + timedelta(days=1)
        raw_events = list_events(start=start, end=end)
    except Exception:  # noqa: BLE001
        logger.warning("calendar.list_events failed", exc_info=True)
        return None

    events_by_day: dict[date, list[dict[str, Any]]] = {d: [] for d in slot_dates}
    for ev in raw_events or []:
        s = getattr(ev, "start", None)
        e = getattr(ev, "end", None)
        if s is None or e is None:
            continue
        d = s.date() if hasattr(s, "date") else None
        if d is None:
            continue
        events_by_day.setdefault(d, []).append(
            {
                "start": {"dateTime": s.isoformat()},
                "end": {"dateTime": e.isoformat()},
            }
        )
    return events_by_day


def _fetch_gmail_replies(gmail: Any, thread_id: str) -> list[dict[str, Any]]:
    """Best-effort reply fetch. Adapter contract:
        gmail.list_thread_messages(thread_id) -> list[dict{'body': str, ...}]
    Returns [] on any error so the polling job stays robust.
    """
    if not thread_id:
        return []
    for fn_name in ("list_thread_messages", "get_thread_messages", "read_thread"):
        fn = getattr(gmail, fn_name, None)
        if callable(fn):
            try:
                result = fn(thread_id)
                return list(result) if result else []
            except Exception as exc:  # noqa: BLE001
                logger.warning("Gmail reply fetch via %s failed: %s", fn_name, exc)
                return []
    return []


def check_polling_status(
    db: Any,
    request_id: str,
    *,
    gmail: Any | None = None,
    anthropic_client: Any | None = None,
    cost_tracker: Any | None = None,
    calendar: Any | None = None,
    scoring_config: ScoringConfig | None = None,
) -> dict[str, Any]:
    """Check a POLLING request for new Gmail replies and summarise state.

    For each participant with a ``gmail_thread_id`` and no recorded response,
    fetch replies, parse the latest body via ``parse_response``, and record
    ``yes``/``if_needed``/``no`` per slot.

    Returns::
        {
            "request_id": ...,
            "status": <current status>,
            "responded": <int>,
            "pending": <int>,
            "total_participants": <int>,
            "new_responses": <int>,
            "consensus_slot_id": <int | None>,
            "parse_errors": [...],
        }

    Does NOT transition the state — the caller (polling job or owner tool)
    decides what to do based on the summary.
    """
    req = sched_db.get_request(db, request_id)
    if req is None:
        return {"error": f"request {request_id!r} not found"}

    existing = sched_db.get_responses(db, request_id)
    already_responded: set[int] = {r["participant_id"] for r in existing}
    new_responses = 0
    parse_errors: list[str] = []

    if gmail is not None and anthropic_client is not None:
        for p in req.participants:
            if p.db_id is None or p.db_id in already_responded:
                continue

            # We need the gmail_thread_id — re-read from DB.
            row = db._conn.execute(
                "SELECT gmail_thread_id FROM scheduling_participants WHERE id = ?",
                (p.db_id,),
            ).fetchone()
            thread_id = row["gmail_thread_id"] if row else None
            if not thread_id:
                continue

            messages = _fetch_gmail_replies(gmail, thread_id)
            if not messages:
                continue

            latest = messages[-1]
            body = latest.get("body") or latest.get("text") or ""
            if not body:
                continue

            parsed = parse_response(
                participant_name=p.name,
                slots=req.slots,
                reply_text=body,
                anthropic_client=anthropic_client,
                cost_tracker=cost_tracker,
                participant_timezone=p.timezone,
            )

            if "error" in parsed:
                parse_errors.append(f"{p.name}: {parsed['error']}")
                continue

            if "counter_proposal" in parsed:
                parse_errors.append(f"{p.name}: counter-proposal — {parsed['counter_proposal']}")
                continue

            responses_map = parsed.get("responses") or {}
            recorded_here = 0
            for slot_id_str, verdict in responses_map.items():
                if verdict not in ("yes", "if_needed", "no"):
                    continue
                try:
                    slot_id = int(slot_id_str)
                except (TypeError, ValueError):
                    continue
                try:
                    sched_db.record_response(
                        db,
                        request_id=request_id,
                        participant_db_id=p.db_id,
                        slot_db_id=slot_id,
                        response=verdict,
                    )
                    recorded_here += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("record_response failed: %s", exc)
            if recorded_here:
                new_responses += 1
                already_responded.add(p.db_id)

    # Recompute participant coverage after recording.
    all_responses = sched_db.get_responses(db, request_id)
    responded_ids = {r["participant_id"] for r in all_responses}
    total = len(req.participants)
    responded = sum(1 for p in req.participants if p.db_id in responded_ids)
    pending = total - responded

    # Pass fresh calendar events (if a calendar tool was injected) so the
    # re-score path picks a slot that is actually still free today.
    owner_events = _fetch_owner_events_for_slots(calendar, req)
    consensus_slot = find_consensus(
        db,
        request_id,
        owner_events_by_day=owner_events,
        scoring_config=scoring_config,
    )

    return {
        "request_id": request_id,
        "status": req.status,
        "responded": responded,
        "pending": pending,
        "total_participants": total,
        "new_responses": new_responses,
        "consensus_slot_id": consensus_slot.db_id if consensus_slot else None,
        "parse_errors": parse_errors,
    }


# ---------------------------------------------------------------------------
# Consensus detection
# ---------------------------------------------------------------------------


def find_consensus(
    db: Any,
    request_id: str,
    *,
    owner_events_by_day: dict[date, list[dict[str, Any]]] | None = None,
    scoring_config: ScoringConfig | None = None,
) -> TimeSlot | None:
    """Return the slot where ALL participants voted ``yes`` or ``if_needed``.

    - A participant who has not responded at all counts as "not yes" for
      every slot (returns None while anyone is pending).
    - A single ``no`` for a slot disqualifies that slot.
    - If multiple slots qualify, the highest-scoring one is returned.

    If ``owner_events_by_day`` is provided, qualifying slots are re-scored
    against the fresh calendar before picking a winner. Stored ``.score``
    values were computed at PROPOSING time and can go stale during POLLING
    (up to 48h) as the owner accepts new meetings that overlap proposed
    slots. Passing fresh events lets the coordinator prefer a slot that is
    still actually free today.

    Returns None if no slot has unanimous acceptance yet.
    """
    req = sched_db.get_request(db, request_id)
    if req is None or not req.slots or not req.participants:
        return None

    responses = sched_db.get_responses(db, request_id)
    participant_ids = {p.db_id for p in req.participants if p.db_id is not None}
    total = len(participant_ids)

    # Build (slot_id) -> {participant_id: verdict}
    per_slot: dict[int, dict[int, str]] = {}
    for r in responses:
        sid = r["slot_id"]
        pid = r["participant_id"]
        verdict = r["response"]
        per_slot.setdefault(sid, {})[pid] = verdict

    qualifying: list[TimeSlot] = []
    for slot in req.slots:
        if slot.db_id is None:
            continue
        votes = per_slot.get(slot.db_id, {})
        # Require every participant to have voted yes/if_needed.
        if len(votes) < total:
            continue
        if not participant_ids.issubset(votes.keys()):
            continue
        if all(votes[pid] in ("yes", "if_needed") for pid in participant_ids):
            qualifying.append(slot)

    if not qualifying:
        return None

    if owner_events_by_day is None:
        return max(qualifying, key=lambda s: s.score)

    # --- Fresh re-score pass -------------------------------------------------
    # Recompute scores against the caller-provided calendar snapshot. We
    # don't mutate the persisted slots — this is a read-time correction
    # that stays local to this call.
    config = scoring_config or ScoringConfig()
    owner_tz = req.preferred_timezone or "UTC"
    range_start = req.date_range_start
    range_end = req.date_range_end

    # Pre-compute per-day busy intervals + event counts from the fresh feed.
    busy_by_day: dict[date, list[tuple[datetime, datetime]]] = {}
    events_per_day: dict[date, int] = {}
    for d, events in owner_events_by_day.items():
        busy_by_day[d] = events_to_busy_intervals(events, owner_tz)
        events_per_day[d] = len(events)

    def _find_conflict_fresh(
        start: datetime,
        end: datetime,
    ) -> str | None:
        from zoneinfo import ZoneInfo

        local_day = start.astimezone(ZoneInfo(owner_tz)).date()
        for bs, be in busy_by_day.get(local_day, []):
            if start < be and end > bs:
                return f"conflict:{bs.isoformat()}"
        return None

    rescored: list[tuple[TimeSlot, float]] = []
    for slot in qualifying:
        from zoneinfo import ZoneInfo

        local_day = slot.start_time.astimezone(ZoneInfo(owner_tz)).date()
        busy_today = busy_by_day.get(local_day, [])
        requires_move = _find_conflict_fresh(slot.start_time, slot.end_time)
        fresh_score = compute_score(
            slot.start_time,
            slot.end_time,
            req.participants,
            busy=busy_today,
            events_per_day=events_per_day,
            range_start=range_start,
            range_end=range_end,
            owner_tz=owner_tz,
            requires_move=requires_move,
            config=config,
        )
        rescored.append((slot, fresh_score))

    # Prefer the highest fresh score. Tie-breaker: fall back to stored score
    # so this remains deterministic even when the fresh calendar is empty.
    rescored.sort(key=lambda ss: (ss[1], ss[0].score), reverse=True)
    return rescored[0][0]


# ---------------------------------------------------------------------------
# record_decision — owner actions (approve / reject / cancel / book / rework)
# ---------------------------------------------------------------------------


def record_decision(
    db: Any,
    request_id: str,
    action: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Dispatch an owner decision on a scheduling request.

    Actions:
        ``approve`` — OWNER_REVIEW → POLLING, and send outreach. Kwargs:
            bot (optional), gmail (optional), owner_name, owner_timezone.
        ``reject`` — OWNER_REVIEW → PROPOSING (re-score).
        ``cancel`` — any non-terminal → CANCELLED.
        ``book`` — CONVERGED → BOOKED. Phase-B caveat: does NOT create a
            calendar event. Kwargs (optional): slot_id.
        ``rework`` — POLLING → OWNER_REVIEW (partial responses, owner decides).

    Returns ``{"status": "ok", "action": ..., "new_status": ..., ...}``
    or ``{"status": "error", "reason": ...}``.
    """
    req = sched_db.get_request(db, request_id)
    if req is None:
        return {"status": "error", "reason": f"request {request_id!r} not found"}

    current = _coerce(req.status)

    if action == "approve":
        if current != SchedulingStatus.OWNER_REVIEW:
            return {
                "status": "error",
                "reason": f"approve requires OWNER_REVIEW, got {current.value}",
            }
        transition(db, request_id, current, SchedulingStatus.POLLING)
        bot = kwargs.get("bot")
        gmail = kwargs.get("gmail")
        owner_name = kwargs.get("owner_name", "your host")
        owner_timezone = kwargs.get("owner_timezone", req.preferred_timezone or "UTC")
        summary = execute_outreach(
            request=req,
            slots=req.slots,
            bot=bot,
            gmail=gmail,
            owner_name=owner_name,
            owner_timezone=owner_timezone,
            db=db,
        )
        return {
            "status": "ok",
            "action": action,
            "new_status": SchedulingStatus.POLLING.value,
            "outreach_summary": summary,
        }

    if action == "reject":
        if current != SchedulingStatus.OWNER_REVIEW:
            return {
                "status": "error",
                "reason": f"reject requires OWNER_REVIEW, got {current.value}",
            }
        transition(db, request_id, current, SchedulingStatus.PROPOSING)
        return {
            "status": "ok",
            "action": action,
            "new_status": SchedulingStatus.PROPOSING.value,
        }

    if action == "cancel":
        if current in (
            SchedulingStatus.BOOKED,
            SchedulingStatus.CANCELLED,
            SchedulingStatus.EXPIRED,
        ):
            return {
                "status": "error",
                "reason": f"cannot cancel from terminal state {current.value}",
            }
        transition(db, request_id, current, SchedulingStatus.CANCELLED)
        return {
            "status": "ok",
            "action": action,
            "new_status": SchedulingStatus.CANCELLED.value,
        }

    if action == "book":
        if current != SchedulingStatus.CONVERGED:
            return {
                "status": "error",
                "reason": f"book requires CONVERGED, got {current.value}",
            }
        transition(db, request_id, current, SchedulingStatus.BOOKED)
        return {
            "status": "ok",
            "action": action,
            "new_status": SchedulingStatus.BOOKED.value,
            "slot_id": kwargs.get("slot_id"),
            "phase_b_note": (
                "Calendar event creation is deferred to Phase B. "
                "Please create the event manually in your calendar."
            ),
        }

    if action == "rework":
        if current != SchedulingStatus.POLLING:
            return {
                "status": "error",
                "reason": f"rework requires POLLING, got {current.value}",
            }
        transition(db, request_id, current, SchedulingStatus.OWNER_REVIEW)
        return {
            "status": "ok",
            "action": action,
            "new_status": SchedulingStatus.OWNER_REVIEW.value,
        }

    return {"status": "error", "reason": f"unknown action: {action!r}"}


__all__ = [
    "InvalidTransition",
    "_TRANSITIONS",
    "check_polling_status",
    "find_consensus",
    "record_decision",
    "start_scheduling",
    "transition",
]
