"""Google Calendar tool with conflict detection.

Layer 1: calendar double-booking is silent and painful — every create
runs `find_conflicts` first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import Any

try:
    from googleapiclient.discovery import Resource, build  # type: ignore[import-untyped]
except ImportError as e:
    raise ImportError(
        "cosinabox[google] extra is required. Run: pip install 'cosinabox[google]'"
    ) from e

from cosinabox.tools.google.auth import build_all_credentials


class CalendarConflict(Exception):
    """Raised when create_event would overlap an existing event."""

    def __init__(self, conflicts: list[CalendarEvent]) -> None:
        self.conflicts = conflicts
        msg = ", ".join(f"{c.summary} ({c.start.isoformat()})" for c in conflicts)
        super().__init__(f"Conflicts: {msg}")


@dataclass
class CalendarEvent:
    id: str
    summary: str
    start: datetime
    end: datetime
    attendees: list[str] = field(default_factory=list)


def _parse_dt(value: dict[str, Any]) -> datetime:
    raw = value.get("dateTime") or value.get("date")
    dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    # All-day events produce naive datetimes (just a date). Normalize to UTC.
    if dt.tzinfo is None:
        # Use midnight UTC for all-day events
        dt = datetime.combine(dt.date(), time(0, 0), tzinfo=UTC)
    return dt


def _list_events_for_service(
    service: Resource, calendar_id: str, start: datetime, end: datetime
) -> list[CalendarEvent]:
    resp = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return [
        CalendarEvent(
            id=item["id"],
            summary=item.get("summary", ""),
            start=_parse_dt(item["start"]),
            end=_parse_dt(item["end"]),
            attendees=[a.get("email", "") for a in item.get("attendees", []) if a.get("email")],
        )
        for item in resp.get("items", [])
    ]


class CalendarTool:
    def __init__(
        self,
        *,
        service: Resource | None = None,
        services: list[Resource] | None = None,
        calendar_id: str = "primary",
    ) -> None:
        if services is not None:
            self._services = services
        elif service is not None:
            self._services = [service]
        else:
            self._services = [
                build("calendar", "v3", credentials=cred) for cred in build_all_credentials()
            ]
        # Backwards compat: expose first service as .service
        self.service = self._services[0]
        self.calendar_id = calendar_id

    def list_events(self, *, start: datetime, end: datetime) -> list[CalendarEvent]:
        seen: set[str] = set()
        out: list[CalendarEvent] = []
        for svc in self._services:
            for evt in _list_events_for_service(svc, self.calendar_id, start, end):
                if evt.id not in seen:
                    seen.add(evt.id)
                    out.append(evt)
        return out

    def find_conflicts(self, *, start: datetime, end: datetime) -> list[CalendarEvent]:
        existing = self.list_events(start=start, end=end)
        return [e for e in existing if e.start < end and e.end > start]

    # Time hint windows: (start_hour, start_min, end_hour, end_min)
    _TIME_WINDOWS: dict[str, tuple[int, int, int, int]] = {
        "morning": (9, 0, 12, 0),
        "lunch": (11, 30, 14, 0),
        "afternoon": (12, 0, 18, 0),
        "evening": (18, 0, 22, 0),
        "dinner": (18, 0, 22, 0),
        "coffee": (9, 0, 11, 0),
        "breakfast": (8, 0, 10, 0),
        "any": (9, 0, 22, 0),
    }

    def find_free_time(
        self,
        *,
        date: datetime,
        duration_minutes: int,
        time_hint: str = "any",
    ) -> list[tuple[datetime, datetime]]:
        """Find available time slots on a given date.

        Args:
            date: The date to check (time component ignored, uses date only).
            duration_minutes: Minimum slot duration in minutes.
            time_hint: Filter window — 'morning', 'afternoon', 'evening',
                'lunch', 'coffee', 'breakfast', 'dinner', or 'any'.

        Returns:
            List of (start, end) tuples representing free slots.
        """
        hint = time_hint.lower().strip()
        window = self._TIME_WINDOWS.get(hint, self._TIME_WINDOWS["any"])
        tz = date.tzinfo
        day = date.replace(hour=0, minute=0, second=0, microsecond=0)
        work_start = day.replace(hour=window[0], minute=window[1])
        work_end = day.replace(hour=window[2], minute=window[3])

        events = self.list_events(start=work_start, end=work_end)

        # Collect busy intervals, skip all-day events (no time component)
        busy: list[tuple[datetime, datetime]] = []
        for evt in events:
            s = max(evt.start, work_start)
            e = min(evt.end, work_end)
            if s < e:
                busy.append((s, e))

        # Merge overlapping intervals
        busy.sort()
        merged: list[tuple[datetime, datetime]] = []
        for s, e in busy:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))

        # Compute free gaps
        required = timedelta(minutes=duration_minutes)
        free_slots: list[tuple[datetime, datetime]] = []
        cursor = work_start
        for s, e in merged:
            if s - cursor >= required:
                free_slots.append((cursor, s))
            cursor = max(cursor, e)
        if work_end - cursor >= required:
            free_slots.append((cursor, work_end))

        return free_slots

    def create_event(
        self,
        *,
        summary: str,
        start: datetime,
        end: datetime,
        attendees: list[str] | None = None,
        allow_conflict: bool = False,
    ) -> CalendarEvent:
        if not allow_conflict:
            conflicts = self.find_conflicts(start=start, end=end)
            if conflicts:
                raise CalendarConflict(conflicts)
        body: dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
        }
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        resp = self._services[0].events().insert(calendarId=self.calendar_id, body=body).execute()
        return CalendarEvent(
            id=resp["id"],
            summary=resp.get("summary", ""),
            start=_parse_dt(resp["start"]),
            end=_parse_dt(resp["end"]),
            attendees=[a.get("email", "") for a in resp.get("attendees", []) if a.get("email")],
        )
