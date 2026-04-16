"""Backchannel / move engine — priority classification + move proposals.

Ported from cos-agent/src/scheduling/backchannel.py, converted to sync and
made OSS-friendly: no hardcoded names, orgs, or domains. Keyword lists and
VIP domains are passed in via `PriorityConfig` (empty by default — callers
supply their own opinionated lists in `integrations.yaml`).

This module is pure algorithm: no calendar I/O. Move execution and undo
(which require Google Calendar credentials) are the responsibility of the
coordinator layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from cosinabox.scheduling.models import Participant, TimeSlot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class PriorityConfig:
    """Configurable priority classification inputs.

    Defaults are deliberately conservative: empty `immovable_keywords`,
    `high_priority_keywords`, and `vip_domains` so an OSS user who installs
    the engine without custom config will never have an event mis-classified
    as "immovable" based on a keyword opinion we didn't ask them for.

    `low_priority_keywords` keeps generic personal-time defaults (focus
    block, tentative, lunch, etc.) — these are broadly safe to move and
    rarely controversial.
    """

    # Title keywords that force an event to "immovable" (e.g., "board meeting").
    immovable_keywords: list[str] = field(default_factory=list)

    # Title keywords that mark an event as "high" (move-avoid unless last resort).
    high_priority_keywords: list[str] = field(default_factory=list)

    # Title keywords that mark an event as "low" (safely moveable).
    # Default list is generic personal-time signals.
    low_priority_keywords: list[str] = field(
        default_factory=lambda: [
            "focus block",
            "focus time",
            "deep work",
            "tentative",
            "coworking",
            "hold",
            "blocked",
            "gym",
            "lunch",
            "break",
        ]
    )

    # Attendee email-domain suffixes that mark an event as immovable
    # (e.g., [".gov", "@investor.com"]). Matched case-insensitively against
    # the domain portion of each attendee email.
    vip_domains: list[str] = field(default_factory=list)

    # Cap on the number of move proposals surfaced per scheduling request.
    # Keeps the owner's review burden bounded.
    max_moves_per_request: int = 2

    # Events starting within this window from "now" are always immovable
    # regardless of keywords — too short notice to reschedule politely.
    proximity_hours: int = 24

    # Workday envelope used when searching for an alternative slot for a
    # displaced event.
    alt_search_day_start_hour: int = 8
    alt_search_day_end_hour: int = 19
    alt_search_step_minutes: int = 30


# ---------------------------------------------------------------------------
# Priority classification
# ---------------------------------------------------------------------------


def _matches_any(text: str, keywords: list[str]) -> bool:
    """Case-insensitive substring match against any keyword."""
    if not keywords:
        return False
    lower = text.lower()
    return any(kw.lower() in lower for kw in keywords)


def _domain_matches_vip(email: str, vip_domains: list[str]) -> bool:
    """Return True if `email`'s domain matches any VIP suffix.

    Matches are substring-based on the domain portion so ".gov" catches
    "edb.gov.sg" and "@client.com" catches "alice@client.com".
    """
    if not vip_domains or "@" not in email:
        return False
    domain = email.rsplit("@", 1)[-1].lower()
    for suffix in vip_domains:
        s = suffix.lower().lstrip("@")
        if s and s in domain:
            return True
    return False


def classify_priority(
    event: dict[str, Any],
    config: PriorityConfig,
    *,
    now: datetime | None = None,
) -> str:
    """Classify a calendar event's priority for move decisions.

    Returns one of: "immovable" | "high" | "medium" | "low".

    Order of checks:
      1. Proximity guard — events starting within `config.proximity_hours`
         are always immovable (too late to reschedule politely).
      2. Title keyword match (immovable > low > high — low wins over high
         because an event titled "focus time with partner" is personal time
         the owner can reclaim, not a partner meeting).
      3. VIP domain attendee match → immovable.
      4. Tentative status → low.
      5. Attendee-count heuristic → high (>=3 external) / medium (>=1).
      6. Common-sync keyword → medium; else medium by default.

    `now` is injectable for testability. Defaults to UTC now.
    """
    title = (event.get("summary") or "").lower()
    status = (event.get("status") or "confirmed").lower()
    attendees = event.get("attendees") or []

    # --- 1. Proximity guard ---
    start_str = (event.get("start") or {}).get("dateTime")
    if start_str:
        try:
            event_start = datetime.fromisoformat(start_str)
            now_dt = now or datetime.now(ZoneInfo("UTC"))
            # Ensure both sides are timezone-aware for subtraction.
            if event_start.tzinfo is None:
                event_start = event_start.replace(tzinfo=ZoneInfo("UTC"))
            if now_dt.tzinfo is None:
                now_dt = now_dt.replace(tzinfo=ZoneInfo("UTC"))
            if event_start - now_dt < timedelta(hours=config.proximity_hours):
                return "immovable"
        except (ValueError, TypeError):
            # Malformed date — fall through to keyword-based checks.
            pass

    # --- 2. Title keyword matching ---
    if _matches_any(title, config.immovable_keywords):
        return "immovable"
    if _matches_any(title, config.low_priority_keywords):
        return "low"
    if _matches_any(title, config.high_priority_keywords):
        return "high"

    # --- 3. VIP domain attendee check ---
    external_count = 0
    for att in attendees:
        if att.get("self"):
            continue
        email = (att.get("email") or "").lower()
        if not email:
            continue
        external_count += 1
        if _domain_matches_vip(email, config.vip_domains):
            return "immovable"

    # --- 4. Tentative status ---
    if status == "tentative":
        return "low"

    # --- 5. Attendee-count heuristic ---
    if external_count >= 3:
        return "high"
    if external_count >= 1:
        return "medium"

    # --- 6. Common-sync keyword → medium ---
    for kw in ("standup", "sync", "check-in", "checkin", "huddle", "retro"):
        if kw in title:
            return "medium"

    return "medium"


# ---------------------------------------------------------------------------
# Move proposal engine
# ---------------------------------------------------------------------------


def _find_alternative_time(
    day: date,
    duration: timedelta,
    exclude_start: datetime,
    exclude_end: datetime,
    existing_events: list[dict[str, Any]],
    owner_tz: str,
    config: PriorityConfig,
) -> str | None:
    """Find an alternative time slot on the same day for a displaced event.

    Returns an ISO-formatted start datetime string, or None if no gap fits.
    """
    tz = ZoneInfo(owner_tz)
    day_start = datetime(
        day.year,
        day.month,
        day.day,
        config.alt_search_day_start_hour,
        0,
        tzinfo=tz,
    )
    day_end = datetime(
        day.year,
        day.month,
        day.day,
        config.alt_search_day_end_hour,
        0,
        tzinfo=tz,
    )

    busy: list[tuple[datetime, datetime]] = []
    for ev in existing_events:
        s_str = (ev.get("start") or {}).get("dateTime")
        e_str = (ev.get("end") or {}).get("dateTime")
        if s_str and e_str:
            try:
                s = datetime.fromisoformat(s_str).astimezone(tz)
                e = datetime.fromisoformat(e_str).astimezone(tz)
                busy.append((s, e))
            except (ValueError, TypeError):
                continue

    # Don't propose sliding the displaced event into the slot we're freeing.
    busy.append((exclude_start.astimezone(tz), exclude_end.astimezone(tz)))
    busy.sort()

    cursor = day_start
    step = timedelta(minutes=config.alt_search_step_minutes)
    while cursor + duration <= day_end:
        end = cursor + duration
        conflicts = any(cursor < be and end > bs for bs, be in busy)
        if not conflicts:
            return cursor.isoformat()
        cursor += step

    return None


def propose_moves(
    *,
    candidate_slots: list[TimeSlot],
    owner_events: list[dict[str, Any]],
    owner_timezone: str,
    config: PriorityConfig | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Find moveable conflicts for the top candidate slots.

    For each candidate slot that overlaps an owner event, classify that
    event's priority. Skip "immovable" and "high" (don't propose moving
    them). For "medium"/"low", find an alternative time on the same day
    and emit a move proposal.

    Returns a list of dicts:
        {
          "slot": TimeSlot,
          "conflict_event": dict (the Google Calendar event),
          "priority": "medium" | "low",
          "alternative_time": str (ISO) | None,
          "score_if_moved": float,
        }

    Capped at `config.max_moves_per_request` proposals.
    """
    config = config or PriorityConfig()
    proposals: list[dict[str, Any]] = []
    tz = ZoneInfo(owner_timezone)

    for slot in candidate_slots:
        if len(proposals) >= config.max_moves_per_request:
            break

        slot_start = slot.start_time.astimezone(tz)
        slot_end = slot.end_time.astimezone(tz)

        for ev in owner_events:
            start_str = (ev.get("start") or {}).get("dateTime")
            end_str = (ev.get("end") or {}).get("dateTime")
            if not start_str or not end_str:
                continue

            try:
                ev_start = datetime.fromisoformat(start_str).astimezone(tz)
                ev_end = datetime.fromisoformat(end_str).astimezone(tz)
            except (ValueError, TypeError):
                continue

            # Overlap check.
            if slot_start >= ev_end or slot_end <= ev_start:
                continue

            priority = classify_priority(ev, config, now=now)
            if priority in ("immovable", "high"):
                continue

            ev_duration = ev_end - ev_start
            alternative = _find_alternative_time(
                ev_start.date(),
                ev_duration,
                slot_start,
                slot_end,
                owner_events,
                owner_timezone,
                config,
            )

            proposals.append(
                {
                    "slot": slot,
                    "conflict_event": ev,
                    "priority": priority,
                    "alternative_time": alternative,
                    # Small bonus — freeing a preferred slot is worth a little
                    # more than the raw score. Kept intentionally modest.
                    "score_if_moved": slot.score + 0.15,
                }
            )

            if len(proposals) >= config.max_moves_per_request:
                break

    return proposals


# ---------------------------------------------------------------------------
# Backchannel message formatting
# ---------------------------------------------------------------------------


def format_backchannel_message(
    *,
    request_title: str,
    slot: TimeSlot,
    conflict_event: dict[str, Any],
    priority: str,
    alternative_time: str | None,
    participants: list[Participant],
    owner_timezone: str,
) -> str:
    """Format the backchannel DM content for the owner about a potential move.

    Pure string construction; no I/O.
    """
    tz = ZoneInfo(owner_timezone)
    slot_start = slot.start_time.astimezone(tz)
    slot_end = slot.end_time.astimezone(tz)

    conflict_title = conflict_event.get("summary") or "(No title)"
    conflict_start_str = (conflict_event.get("start") or {}).get("dateTime", "")
    conflict_end_str = (conflict_event.get("end") or {}).get("dateTime", "")

    try:
        conflict_start = datetime.fromisoformat(conflict_start_str).astimezone(tz)
        conflict_end = datetime.fromisoformat(conflict_end_str).astimezone(tz)
        conflict_time = (
            f"{conflict_start.strftime('%I:%M %p').lstrip('0')} - "
            f"{conflict_end.strftime('%I:%M %p').lstrip('0')}"
        )
    except (ValueError, TypeError):
        conflict_time = "unknown time"

    tz_label = slot_start.tzname() or owner_timezone
    slot_time = (
        f"{slot_start.strftime('%a %d %b, %I:%M %p').lstrip('0')} - "
        f"{slot_end.strftime('%I:%M %p').lstrip('0')} {tz_label}"
    )

    participant_names = ", ".join(p.name for p in participants)

    lines = [
        f"Backchannel: calendar move needed for '{request_title}'",
        "",
        f"Best slot for {participant_names}:",
        f"  {slot_time} (score: {slot.score:.2f})",
        "",
        f"Conflicts with: {conflict_title}",
        f"  Currently at: {conflict_time}",
        f"  Priority: {priority}",
    ]

    if alternative_time:
        try:
            alt_dt = datetime.fromisoformat(alternative_time).astimezone(tz)
            alt_str = alt_dt.strftime("%I:%M %p").lstrip("0")
            lines.append(f"  Proposed move to: {alt_str}")
        except (ValueError, TypeError):
            lines.append(f"  Proposed move to: {alternative_time}")
    else:
        lines.append("  No good alternative time found on the same day.")

    return "\n".join(lines)
