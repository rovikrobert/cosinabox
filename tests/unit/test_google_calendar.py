from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from cosinabox.tools.google.calendar import CalendarConflict, CalendarTool


def _fake_service(events: list[dict]) -> MagicMock:
    svc = MagicMock()
    list_call = MagicMock()
    list_call.execute.return_value = {"items": events}
    svc.events.return_value.list.return_value = list_call
    insert_call = MagicMock()
    insert_call.execute.return_value = {
        "id": "new-evt",
        "summary": "X",
        "start": {"dateTime": "2026-04-12T10:00:00+00:00"},
        "end": {"dateTime": "2026-04-12T11:00:00+00:00"},
    }
    svc.events.return_value.insert.return_value = insert_call
    return svc


def test_find_conflicts_returns_overlapping_events() -> None:
    existing = [
        {
            "id": "e1",
            "summary": "Standup",
            "start": {"dateTime": "2026-04-12T10:00:00+00:00"},
            "end": {"dateTime": "2026-04-12T10:30:00+00:00"},
        }
    ]
    tool = CalendarTool(service=_fake_service(existing))
    start = datetime(2026, 4, 12, 10, 15, tzinfo=timezone.utc)
    end = start + timedelta(minutes=30)
    conflicts = tool.find_conflicts(start=start, end=end)
    assert len(conflicts) == 1
    assert conflicts[0].id == "e1"


def test_create_event_blocks_when_conflict_present() -> None:
    existing = [
        {
            "id": "e1",
            "summary": "Standup",
            "start": {"dateTime": "2026-04-12T10:00:00+00:00"},
            "end": {"dateTime": "2026-04-12T10:30:00+00:00"},
        }
    ]
    tool = CalendarTool(service=_fake_service(existing))
    with pytest.raises(CalendarConflict):
        tool.create_event(
            summary="Coffee",
            start=datetime(2026, 4, 12, 10, 15, tzinfo=timezone.utc),
            end=datetime(2026, 4, 12, 10, 45, tzinfo=timezone.utc),
        )


def test_create_event_with_override_succeeds() -> None:
    existing = [
        {
            "id": "e1",
            "summary": "Standup",
            "start": {"dateTime": "2026-04-12T10:00:00+00:00"},
            "end": {"dateTime": "2026-04-12T10:30:00+00:00"},
        }
    ]
    tool = CalendarTool(service=_fake_service(existing))
    evt = tool.create_event(
        summary="Coffee",
        start=datetime(2026, 4, 12, 10, 15, tzinfo=timezone.utc),
        end=datetime(2026, 4, 12, 10, 45, tzinfo=timezone.utc),
        allow_conflict=True,
    )
    assert evt.id == "new-evt"
