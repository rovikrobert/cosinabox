"""Google Calendar tool with conflict detection.

Layer 1: calendar double-booking is silent and painful — every create
runs `find_conflicts` first.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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


def _parse_dt(value: dict[str, Any]) -> datetime:
    raw = value.get("dateTime") or value.get("date")
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))


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
        )
