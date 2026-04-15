"""Group scheduling tool definitions + handlers for Claude API.

Three tools for multi-person meeting coordination:
- schedule_group_meeting: start a new scheduling flow (scores candidate slots,
  surfaces for owner review)
- scheduling_status: list active requests, or show detail for one
- scheduling_respond: record an owner decision (approve / reject / cancel /
  book / rework)

Phase B caveat: the ``book`` action transitions the state but does NOT create
a calendar event — calendar-event booking is deferred to Plan 5. Handlers
surface this to the user so they create the event manually.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any

from cosinabox.scheduling import coordinator as sched_coordinator
from cosinabox.scheduling import db as sched_db
from cosinabox.scheduling.models import Participant

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


def build_scheduling_tool_definitions(owner_name: str) -> list[dict[str, Any]]:
    """Return the 3 Anthropic tool schemas, interpolating ``owner_name``.

    Generic for OSS use — no hardcoded user names. ``owner_name`` is woven
    into descriptions so Claude understands whose calendar/preferences
    are authoritative.
    """
    return [
        {
            "name": "schedule_group_meeting",
            "description": (
                f"Start a group scheduling flow on behalf of {owner_name}. "
                "Finds optimal times across all participant timezones "
                "(excluding 1am-6am local for everyone), then surfaces "
                f"the top candidate slots to {owner_name} for review before "
                "reaching out to participants."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Meeting title.",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Meeting duration in minutes.",
                    },
                    "participants": {
                        "type": "array",
                        "description": (
                            f"List of participants (excluding {owner_name})."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Participant name.",
                                },
                                "email": {
                                    "type": "string",
                                    "description": "Email address (optional).",
                                },
                                "timezone": {
                                    "type": "string",
                                    "description": (
                                        "IANA timezone (e.g., 'Europe/Berlin'). "
                                        f"If unknown, ask {owner_name}."
                                    ),
                                },
                                "channel": {
                                    "type": "string",
                                    "enum": ["telegram", "gmail"],
                                    "description": (
                                        "Preferred contact channel."
                                    ),
                                },
                            },
                            "required": ["name"],
                        },
                    },
                    "date_range_start": {
                        "type": "string",
                        "description": "Start of date range (YYYY-MM-DD).",
                    },
                    "date_range_end": {
                        "type": "string",
                        "description": "End of date range (YYYY-MM-DD).",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes or context.",
                    },
                },
                "required": [
                    "title",
                    "duration_minutes",
                    "participants",
                    "date_range_start",
                    "date_range_end",
                ],
            },
        },
        {
            "name": "scheduling_status",
            "description": (
                f"List active scheduling requests for {owner_name}, or show "
                "detail (participants, candidate slots, responses) for one "
                "specific request when a request_id is supplied."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "request_id": {
                        "type": "string",
                        "description": (
                            "Optional request ID. If omitted, lists all "
                            "active (non-terminal) requests."
                        ),
                    },
                },
                "required": [],
            },
        },
        {
            "name": "scheduling_respond",
            "description": (
                f"Record {owner_name}'s decision on an existing scheduling "
                "request. Actions: 'approve' (send outreach to participants), "
                "'reject' (re-score / rework slot proposals), "
                "'book' (mark the converged slot as booked — see Phase B "
                "caveat), 'cancel' (abort the request), "
                "'rework' (return from POLLING to owner review)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "request_id": {
                        "type": "string",
                        "description": "Scheduling request ID.",
                    },
                    "action": {
                        "type": "string",
                        "enum": [
                            "approve",
                            "reject",
                            "book",
                            "cancel",
                            "rework",
                        ],
                        "description": "The decision action.",
                    },
                    "slot_id": {
                        "type": "integer",
                        "description": (
                            "Slot ID (optional, relevant for 'book')."
                        ),
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes or rationale.",
                    },
                },
                "required": ["request_id", "action"],
            },
        },
    ]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


_BOOK_PHASE_B_CAVEAT = (
    "Calendar event creation is deferred to Plan 5 — please create "
    "the event manually in Google Calendar."
)


def _format_request_summary(req: Any) -> str:
    """Single-line summary for list views."""
    return (
        f"- [{req.status}] {req.id[:8]}  {req.title}  "
        f"({req.duration_minutes}min, {req.date_range_start}..{req.date_range_end}, "
        f"{len(req.participants)} participants)"
    )


def _format_request_detail(db: Any, req: Any) -> str:
    """Full detail block for one request."""
    responses = sched_db.get_responses(db, req.id)
    responded = len({r["participant_id"] for r in responses})
    lines = [
        f"Title: {req.title}",
        f"ID: {req.id}",
        f"Status: {req.status}",
        f"Duration: {req.duration_minutes} min",
        f"Date range: {req.date_range_start} to {req.date_range_end}",
        f"Participants: {len(req.participants)} ({responded} responded)",
        "",
    ]
    for p in req.participants:
        lines.append(
            f"  - {p.name} ({p.timezone}, via {p.channel}): {p.status}"
        )
    if req.slots:
        lines.append("")
        lines.append(f"Candidate slots: {len(req.slots)}")
        for i, s in enumerate(req.slots[:5], 1):
            flag = " [needs move]" if s.requires_move else ""
            lines.append(
                f"  {i}. [id={s.db_id}] score {s.score:.2f}: "
                f"{s.start_time.isoformat()} - {s.end_time.isoformat()}{flag}"
            )
    return "\n".join(lines)


def build_scheduling_handlers(
    *,
    db: Any,
    coordinator_ctx: dict[str, Any],
    owner_name: str,
    owner_timezone: str,
) -> dict[str, Callable[..., str]]:
    """Build the 3 scheduling handlers.

    ``coordinator_ctx`` is an open-ended dict of dependencies the coordinator
    needs — typically ``{"anthropic_client": ..., "cost_tracker": ...,
    "bot": ..., "gmail": ...}``. Handlers unpack what they need and forward
    the rest to the coordinator.
    """

    def schedule_group_meeting(
        title: str,
        duration_minutes: int,
        participants: list[dict[str, Any]],
        date_range_start: str,
        date_range_end: str,
        notes: str | None = None,
    ) -> str:
        parts = [
            Participant(
                name=p["name"],
                email=p.get("email"),
                timezone=p.get("timezone", owner_timezone),
                channel=p.get("channel", "gmail"),
            )
            for p in participants
        ]
        if not parts:
            return "No participants specified. Please include at least one."

        try:
            rs = date.fromisoformat(date_range_start)
            re_ = date.fromisoformat(date_range_end)
        except ValueError as exc:
            return f"Invalid date format: {exc}. Use YYYY-MM-DD."
        if re_ < rs:
            return "date_range_end must be on or after date_range_start."

        try:
            req = sched_coordinator.start_scheduling(
                db=db,
                participants=parts,
                duration_minutes=duration_minutes,
                date_range_start=rs,
                date_range_end=re_,
                owner_timezone=owner_timezone,
                owner_name=owner_name,
                title=title,
                notes=notes,
                anthropic_client=coordinator_ctx.get("anthropic_client"),
                cost_tracker=coordinator_ctx.get("cost_tracker"),
            )
        except Exception as exc:
            logger.exception("schedule_group_meeting failed")
            return f"Scheduling failed: {exc}"

        if req.status == "cancelled":
            return (
                f"No viable slots found for '{title}' between "
                f"{date_range_start} and {date_range_end}. "
                "Request was auto-cancelled."
            )

        return (
            f"Created scheduling request {req.id} for '{title}'. "
            f"Status: {req.status}. "
            f"{len(req.slots)} candidate slots scored — awaiting review. "
            "Use scheduling_respond with action='approve' to send outreach, "
            "or action='reject' to rework."
        )

    def scheduling_status(request_id: str | None = None) -> str:
        if request_id:
            req = sched_db.get_request(db, request_id)
            if req is None:
                return f"Scheduling request '{request_id}' not found."
            return _format_request_detail(db, req)

        active = sched_db.get_active_requests(
            db,
            status_filter=[
                "proposing", "owner_review", "polling",
                "converged", "backchannel",
            ],
        )
        if not active:
            return "No active scheduling requests."
        lines = [f"{len(active)} active scheduling request(s):"]
        for req in active:
            lines.append(_format_request_summary(req))
        return "\n".join(lines)

    def scheduling_respond(
        request_id: str,
        action: str,
        slot_id: int | None = None,
        notes: str | None = None,
    ) -> str:
        kwargs: dict[str, Any] = {
            "owner_name": owner_name,
            "owner_timezone": owner_timezone,
            "bot": coordinator_ctx.get("bot"),
            "gmail": coordinator_ctx.get("gmail"),
        }
        if slot_id is not None:
            kwargs["slot_id"] = slot_id
        if notes is not None:
            kwargs["notes"] = notes

        try:
            result = sched_coordinator.record_decision(
                db, request_id, action, **kwargs,
            )
        except Exception as exc:
            logger.exception("scheduling_respond failed")
            return f"Decision failed: {exc}"

        if result.get("status") == "error":
            return f"Decision rejected: {result.get('reason', 'unknown error')}"

        new_status = result.get("new_status", "?")
        msg = (
            f"Action '{action}' recorded for {request_id}. "
            f"New status: {new_status}."
        )
        if action == "book":
            msg += " " + _BOOK_PHASE_B_CAVEAT
        if "outreach_summary" in result:
            msg += f"\nOutreach: {result['outreach_summary']}"
        return msg

    return {
        "schedule_group_meeting": schedule_group_meeting,
        "scheduling_status": scheduling_status,
        "scheduling_respond": scheduling_respond,
    }


__all__ = [
    "build_scheduling_tool_definitions",
    "build_scheduling_handlers",
]
