"""Tool registry — builds Claude API tool definitions + handler callables.

Each tool integration defines its own TOOL_DEFINITIONS (Claude schemas) and
a handler function. The registry composes them from tool instances that
app.tools.build_tools() creates (App._build_tools delegates to it).

OSS-friendly: descriptions are generic, no hardcoded user names.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from cosinabox.commitments.migrate_from_keep_warm import looks_like_commitment
from cosinabox.memory.keep_warm_history import archive_note

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Gmail tool definitions
# ---------------------------------------------------------------------------

GMAIL_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "gmail_search",
        "description": (
            "Search emails matching a query. Uses Gmail search syntax "
            "(e.g., 'from:alice@example.com subject:project')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Gmail search query.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max emails to return (default 10).",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "gmail_list_recent",
        "description": (
            "List recent emails from the last N hours. "
            "Good for getting an overview of what's arrived."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Look back this many hours (default 24).",
                    "default": 24,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max emails to return (default 25).",
                    "default": 25,
                },
            },
            "required": [],
        },
    },
    {
        "name": "gmail_compose",
        "description": (
            "Create an email draft. Does NOT send — creates a draft for "
            "the user to review in Gmail. Always confirm recipients and "
            "content with the user before composing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address(es), comma-separated.",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line.",
                },
                "body": {
                    "type": "string",
                    "description": "Email body text.",
                },
                "cc": {
                    "type": "string",
                    "description": "CC recipients, comma-separated (optional).",
                },
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "gmail_send",
        "description": (
            "Send an existing draft by draft ID. Requires explicit user "
            "approval — never send without the user confirming."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_id": {
                    "type": "string",
                    "description": "Draft ID to send (from gmail_compose).",
                },
            },
            "required": ["draft_id"],
        },
    },
]

# ---------------------------------------------------------------------------
# Calendar tool definitions
# ---------------------------------------------------------------------------

CALENDAR_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "calendar_list_events",
        "description": (
            "List calendar events in a date/time range. Returns event titles, times, and attendees."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {
                    "type": "string",
                    "description": "Start of range (ISO 8601, e.g., '2026-04-12T00:00:00+08:00').",
                },
                "end": {
                    "type": "string",
                    "description": "End of range (ISO 8601).",
                },
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "calendar_find_conflicts",
        "description": (
            "Check for scheduling conflicts in a time range. "
            "Returns any events that overlap with the given window."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {
                    "type": "string",
                    "description": "Start of window (ISO 8601).",
                },
                "end": {
                    "type": "string",
                    "description": "End of window (ISO 8601).",
                },
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "calendar_create_event",
        "description": (
            "Create a calendar event. Automatically checks for conflicts "
            "before creating. Supports attendees."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Event title.",
                },
                "start": {
                    "type": "string",
                    "description": "Start time (ISO 8601, e.g., '2026-04-14T10:00:00+08:00').",
                },
                "end": {
                    "type": "string",
                    "description": "End time (ISO 8601).",
                },
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of attendee email addresses (optional).",
                },
            },
            "required": ["summary", "start", "end"],
        },
    },
    {
        "name": "calendar_find_free_time",
        "description": (
            "Find available time slots on a given date. "
            "Returns free windows that fit the requested duration."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date to check (YYYY-MM-DD).",
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "Desired meeting duration in minutes.",
                },
                "time_hint": {
                    "type": "string",
                    "description": (
                        "Optional time preference: 'morning' (9-12), 'lunch' (11:30-14), "
                        "'afternoon' (12-18), 'evening' (18-22), 'coffee' (9-11), "
                        "'any' (9-22, default)."
                    ),
                },
            },
            "required": ["date", "duration_minutes"],
        },
    },
]

# ---------------------------------------------------------------------------
# Attio CRM tool definitions
# ---------------------------------------------------------------------------

ATTIO_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "crm_search_people",
        "description": "Search the CRM for people matching a name query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Name or partial name to search for.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "crm_get_person",
        "description": "Get a person's CRM profile by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Person's name.",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "crm_list_people",
        "description": "List people in the CRM (up to a limit).",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max records to return (default 50).",
                    "default": 50,
                },
            },
            "required": [],
        },
    },
    {
        "name": "keep_warm_set",
        "description": (
            "Flag a person as Keep Warm with a per-person cadence in days. "
            "The morning briefing will surface them as overdue when "
            "days-since-last-contact exceeds their cadence. Use when the user "
            "asks to remember someone (e.g., 'remind me to stay in touch with "
            "Sarah every two weeks'). Cadence is clamped to [1, 365]."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "person": {"type": "string", "description": "Person's name."},
                "cadence_days": {
                    "type": "integer",
                    "description": "How many days between touches (e.g., 14).",
                },
                "note": {
                    "type": "string",
                    "description": "Optional short note (e.g., 'Lead investor').",
                },
            },
            "required": ["person", "cadence_days"],
        },
    },
    {
        "name": "keep_warm_unset",
        "description": (
            "Remove a person from Keep Warm. Use when a relationship is "
            "paused, deprioritized, or the person moved on. Optional note "
            "captures why (e.g., 'deprioritized 2026-05-12')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "person": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["person"],
        },
    },
    {
        "name": "keep_warm_list",
        "description": (
            "List all Keep Warm people, most overdue first. Shows days since "
            "last contact and per-person cadence. Use when the user asks "
            "'who's on Keep Warm' or 'who am I overdue on.'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

# ---------------------------------------------------------------------------
# Fireflies tool definitions
# ---------------------------------------------------------------------------

FIREFLIES_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "fireflies_list_meetings",
        "description": "List recent meeting transcripts from the last N hours.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Look back this many hours (default 24).",
                    "default": 24,
                },
            },
            "required": [],
        },
    },
    {
        "name": "fireflies_get_transcript",
        "description": "Get the full transcript for a specific meeting.",
        "input_schema": {
            "type": "object",
            "properties": {
                "meeting_id": {
                    "type": "string",
                    "description": "Meeting/transcript ID.",
                },
            },
            "required": ["meeting_id"],
        },
    },
]

# ---------------------------------------------------------------------------
# Web search tool definitions
# ---------------------------------------------------------------------------

WEB_SEARCH_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "web_search",
        "description": (
            "Search the web via Google. Returns organic results with titles, links, and snippets."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query.",
                },
                "num": {
                    "type": "integer",
                    "description": "Number of results (default 5, max 10).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
]


# ---------------------------------------------------------------------------
# Handler builders — wrap tool class methods as Claude-callable functions
# ---------------------------------------------------------------------------


def _serialize(obj: Any) -> str:
    """Serialize a tool result to a string for Claude.

    Handles dataclass instances, lists of dataclasses, dicts, and primitives.
    """
    if isinstance(obj, str):
        return obj
    if isinstance(obj, list):
        items = [_serialize_item(item) for item in obj]
        return json.dumps(items, default=str)
    if isinstance(obj, dict):
        normalized = {k: _serialize_item(v) for k, v in obj.items()}
        return json.dumps(normalized, default=str)
    if hasattr(obj, "__dataclass_fields__"):
        return json.dumps(_serialize_item(obj), default=str)
    return str(obj)


def _serialize_item(item: Any) -> Any:
    """Serialize a single item (dataclass or dict) for JSON output."""
    if hasattr(item, "__dataclass_fields__"):
        return {k: str(v) for k, v in item.__dict__.items()}
    return item


def _build_gmail_handlers(gmail: Any) -> dict[str, Callable[..., str]]:
    """Build handler dict from a GmailTool instance."""

    def gmail_search(query: str, max_results: int = 10) -> str:
        results = gmail.search(query, max_results=max_results)
        return _serialize(results)

    def gmail_list_recent(hours: int = 24, max_results: int = 25) -> str:
        results = gmail.list_recent(hours=hours, max_results=max_results)
        return _serialize(results)

    def gmail_compose(
        to: str,
        subject: str,
        body: str,
        cc: str = "",
    ) -> str:
        result = gmail.compose_draft(to=to, subject=subject, body=body, cc=cc)
        return _serialize(result)

    def gmail_send(draft_id: str) -> str:
        result = gmail.send_draft(draft_id=draft_id)
        return _serialize(result)

    return {
        "gmail_search": gmail_search,
        "gmail_list_recent": gmail_list_recent,
        "gmail_compose": gmail_compose,
        "gmail_send": gmail_send,
    }


def _build_calendar_handlers(
    calendar: Any,
    *,
    timezone: str = "UTC",
) -> dict[str, Callable[..., str]]:
    """Build handler dict from a CalendarTool instance."""

    def calendar_list_events(start: str, end: str) -> str:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        results = calendar.list_events(start=start_dt, end=end_dt)
        return _serialize(results)

    def calendar_find_conflicts(start: str, end: str) -> str:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        results = calendar.find_conflicts(start=start_dt, end=end_dt)
        if not results:
            return "No conflicts found."
        return _serialize(results)

    def calendar_create_event(
        summary: str,
        start: str,
        end: str,
        attendees: list[str] | None = None,
    ) -> str:
        from cosinabox.tools.google.calendar import CalendarConflict

        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        try:
            event = calendar.create_event(
                summary=summary,
                start=start_dt,
                end=end_dt,
                attendees=attendees,
            )
            lines = [
                "Event created:",
                f"  Title: {event.summary}",
                f"  When: {event.start.isoformat()} — {event.end.isoformat()}",
                f"  Event ID: {event.id}",
            ]
            return "\n".join(lines)
        except CalendarConflict as exc:
            conflicts = _serialize(exc.conflicts)
            return f"CONFLICT — event not created. Overlapping events:\n{conflicts}"

    def calendar_find_free_time(
        date: str,
        duration_minutes: int,
        time_hint: str = "any",
    ) -> str:
        from zoneinfo import ZoneInfo

        # Parse date string and attach the user's configured timezone
        # so time windows (morning=9-12, etc.) align with their local clock.
        day = datetime.strptime(date, "%Y-%m-%d")
        day = day.replace(tzinfo=ZoneInfo(timezone))

        slots = calendar.find_free_time(
            date=day,
            duration_minutes=duration_minutes,
            time_hint=time_hint,
        )
        if not slots:
            return (
                f"No available slots of {duration_minutes} minutes "
                f"found on {date} (hint: {time_hint})."
            )
        lines = [f"Available slots ({duration_minutes} min+) on {date}:"]
        for slot_start, slot_end in slots:
            slot_dur = int((slot_end - slot_start).total_seconds() // 60)
            lines.append(
                f"  {slot_start.strftime('%H:%M')} — {slot_end.strftime('%H:%M')}  ({slot_dur} min)"
            )
        return "\n".join(lines)

    return {
        "calendar_list_events": calendar_list_events,
        "calendar_find_conflicts": calendar_find_conflicts,
        "calendar_create_event": calendar_create_event,
        "calendar_find_free_time": calendar_find_free_time,
    }


def _build_attio_handlers(
    attio: Any,
    *,
    memory: Any | None = None,
) -> dict[str, Callable[..., str]]:
    """Build handler dict from an AttioClient instance."""

    def crm_search_people(query: str) -> str:
        results = attio.search_people(query)
        return _serialize(results)

    def crm_get_person(name: str) -> str:
        result = attio.get_person(name)
        if result is None:
            return f"No person found matching '{name}'."
        return _serialize(result)

    def crm_list_people(limit: int = 50) -> str:
        results = attio.list_people(limit=limit)
        return _serialize(results)

    def _format_keep_warm_row(p: Any) -> str:
        note_part = f". Note: {p.note}" if p.note else ""
        days = (
            f"{p.days_since}d since last contact"
            if p.days_since is not None
            else "no last contact on record"
        )
        return f"- {p.name} — {days} (cadence: {p.cadence_days}d){note_part}"

    def keep_warm_set(person: str, cadence_days: int, note: str | None = None) -> str:
        # Read current note BEFORE delegating so we can snapshot a change
        current_note: str | None = None
        current_record_id: str | None = None
        if memory is not None and note is not None:
            try:
                profile = attio.get_person(person)
                if profile:
                    current_note = profile.get("keep_warm_note")
                    current_record_id = str(profile.get("id") or "") or None
            except Exception:
                logger.warning(
                    "keep_warm_set: pre-fetch for history snapshot failed (person=%r)",
                    person,
                    exc_info=True,
                )

        try:
            out = attio.set_keep_warm(person=person, cadence_days=cadence_days, note=note)
        except Exception as exc:
            return f"keep_warm_set failed: {exc}"
        if out.get("status") != "ok":
            return f"keep_warm_set failed: {out.get('message', 'unknown')}"

        # Snapshot old note if it existed AND the incoming value differs
        if (
            memory is not None
            and note is not None
            and current_note
            and current_note != note
            and (current_record_id or out.get("record_id"))
        ):
            try:
                archive_note(
                    memory,
                    person_record_id=current_record_id or str(out.get("record_id", "")),
                    person_name=person,
                    note=current_note,
                    reason=None,
                )
            except Exception:
                logger.warning(
                    "keep_warm_set: history archive failed (person=%r)",
                    person,
                    exc_info=True,
                )

        lines = [f"Flagged {out['person']} as Keep Warm (cadence: {out['cadence_days']}d)."]
        if note:
            matched = looks_like_commitment(note)
            if matched:
                lines.append(
                    f'WARNING: note looks commitment-shaped ("{matched}") — '
                    "consider calling commitment_create instead and keeping the "
                    "note as relationship context only."
                )
        return "\n".join(lines)

    def keep_warm_unset(person: str, note: str | None = None) -> str:
        try:
            out = attio.unset_keep_warm(person=person, note=note)
        except Exception as exc:
            return f"keep_warm_unset failed: {exc}"
        if out.get("status") != "ok":
            return f"keep_warm_unset failed: {out.get('message', 'unknown')}"
        return f"Removed {out['person']} from Keep Warm."

    def keep_warm_list() -> str:
        try:
            people = attio.list_keep_warm()
        except Exception as exc:
            return f"keep_warm_list failed: {exc}"
        if not people:
            return "No one flagged as Keep Warm."
        lines = [f"{len(people)} Keep Warm people (most overdue first):"]
        lines.extend(_format_keep_warm_row(p) for p in people)
        return "\n".join(lines)

    return {
        "crm_search_people": crm_search_people,
        "crm_get_person": crm_get_person,
        "crm_list_people": crm_list_people,
        "keep_warm_set": keep_warm_set,
        "keep_warm_unset": keep_warm_unset,
        "keep_warm_list": keep_warm_list,
    }


def _build_fireflies_handlers(fireflies: Any) -> dict[str, Callable[..., str]]:
    """Build handler dict from a FirefliesTool instance."""

    def fireflies_list_meetings(hours: int = 24) -> str:
        results = fireflies.list_recent_meetings(hours=hours)
        return _serialize(results)

    def fireflies_get_transcript(meeting_id: str) -> str:
        result = fireflies.get_transcript(meeting_id)
        return _serialize(result)

    return {
        "fireflies_list_meetings": fireflies_list_meetings,
        "fireflies_get_transcript": fireflies_get_transcript,
    }


def _build_web_search_handlers(web_search: Any) -> dict[str, Callable[..., str]]:
    """Build handler dict from a WebSearchTool instance."""

    def do_web_search(query: str, num: int = 5) -> str:
        results = web_search.search(query, num=min(num, 10))
        return _serialize(results)

    return {"web_search": do_web_search}


# ---------------------------------------------------------------------------
# Public API: build_tool_registry
# ---------------------------------------------------------------------------


def build_tool_registry(
    tool_instances: dict[str, Any],
    *,
    timezone: str = "UTC",
    rela_agent: Any | None = None,
    scheduling_ctx: Any | None = None,  # SchedulingContext or None
    memory: Any | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Callable[..., str]]]:
    """Build Claude API tool definitions and handler dict from tool instances.

    Args:
        tool_instances: Dict from app.tools.build_tools(), e.g.
            {"gmail": GmailTool, "calendar": CalendarTool, ...}
        timezone: User's IANA timezone (e.g. "Asia/Singapore"). Used by
            calendar handlers so time windows align with the user's local clock.

    Returns:
        (tool_definitions, tool_handlers) where:
        - tool_definitions: list of Claude API tool schemas
        - tool_handlers: {"tool_name": callable} for AgentLoop dispatch
    """
    definitions: list[dict[str, Any]] = []
    handlers: dict[str, Callable[..., str]] = {}

    if "gmail" in tool_instances:
        definitions.extend(GMAIL_TOOL_DEFINITIONS)
        handlers.update(_build_gmail_handlers(tool_instances["gmail"]))
        logger.info("Registered %d Gmail tools", len(GMAIL_TOOL_DEFINITIONS))

    if "calendar" in tool_instances:
        definitions.extend(CALENDAR_TOOL_DEFINITIONS)
        handlers.update(_build_calendar_handlers(tool_instances["calendar"], timezone=timezone))
        logger.info("Registered %d Calendar tools", len(CALENDAR_TOOL_DEFINITIONS))

    if "attio" in tool_instances:
        definitions.extend(ATTIO_TOOL_DEFINITIONS)
        handlers.update(_build_attio_handlers(tool_instances["attio"], memory=memory))
        logger.info("Registered %d Attio CRM tools", len(ATTIO_TOOL_DEFINITIONS))

    if "fireflies" in tool_instances:
        definitions.extend(FIREFLIES_TOOL_DEFINITIONS)
        handlers.update(_build_fireflies_handlers(tool_instances["fireflies"]))
        logger.info("Registered %d Fireflies tools", len(FIREFLIES_TOOL_DEFINITIONS))

    if "web_search" in tool_instances:
        definitions.extend(WEB_SEARCH_TOOL_DEFINITIONS)
        handlers.update(_build_web_search_handlers(tool_instances["web_search"]))
        logger.info("Registered %d web search tools", len(WEB_SEARCH_TOOL_DEFINITIONS))

    # Rela query tool (registered if rela agent is available)
    if rela_agent is not None:
        from cosinabox.tools.rela_tool import RELA_QUERY_DEFINITION, rela_query_handler

        definitions.append(RELA_QUERY_DEFINITION)
        handlers["rela_query"] = rela_query_handler(rela_agent)
        logger.info("Registered rela_query tool")

    # Scheduling tools (registered if scheduling_ctx provided)
    if scheduling_ctx is not None:
        from cosinabox.tools.scheduling_tool import (
            build_scheduling_handlers,
            build_scheduling_tool_definitions,
        )

        sched_defs = build_scheduling_tool_definitions(
            scheduling_ctx.owner.name,
        )
        definitions.extend(sched_defs)
        handlers.update(build_scheduling_handlers(scheduling_ctx))
        logger.info("Registered %d scheduling tools", len(sched_defs))

    # Commitments tools (registered when a memory/db instance is available).
    # Agent uses these to create, list, update, close, dismiss, reopen
    # tracked work items — the source of truth for briefing CARRY-OVER /
    # MISSES / NEXT WEEK / PRIORITIES sections.
    if memory is not None:
        from cosinabox.tools.commitments_tool import (
            COMMITMENT_TOOL_DEFINITIONS,
            build_commitment_handlers,
        )

        definitions.extend(COMMITMENT_TOOL_DEFINITIONS)
        handlers.update(build_commitment_handlers(memory))
        logger.info("Registered %d commitment tools", len(COMMITMENT_TOOL_DEFINITIONS))

    # Consistency check: every definition has a matching handler
    def_names = {d["name"] for d in definitions}
    handler_names = set(handlers.keys())
    assert def_names == handler_names, (
        f"Tool definition/handler mismatch: "
        f"defs={def_names - handler_names}, handlers={handler_names - def_names}"
    )

    logger.info("Tool registry: %d tools registered", len(definitions))
    return definitions, handlers
