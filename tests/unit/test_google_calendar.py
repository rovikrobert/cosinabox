from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
    start = datetime(2026, 4, 12, 10, 15, tzinfo=UTC)
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
            start=datetime(2026, 4, 12, 10, 15, tzinfo=UTC),
            end=datetime(2026, 4, 12, 10, 45, tzinfo=UTC),
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
        start=datetime(2026, 4, 12, 10, 15, tzinfo=UTC),
        end=datetime(2026, 4, 12, 10, 45, tzinfo=UTC),
        allow_conflict=True,
    )
    assert evt.id == "new-evt"


# ---------------------------------------------------------------------------
# find_free_time tests
# ---------------------------------------------------------------------------


def test_find_free_time_empty_calendar() -> None:
    tool = CalendarTool(service=_fake_service([]))
    day = datetime(2026, 4, 14, 0, 0, tzinfo=UTC)
    slots = tool.find_free_time(date=day, duration_minutes=30)
    # Full day should be one big slot: 09:00-22:00
    assert len(slots) == 1
    assert slots[0][0].hour == 9
    assert slots[0][1].hour == 22


def test_find_free_time_with_one_meeting() -> None:
    events = [
        {
            "id": "e1",
            "summary": "Standup",
            "start": {"dateTime": "2026-04-14T10:00:00+00:00"},
            "end": {"dateTime": "2026-04-14T10:30:00+00:00"},
        }
    ]
    tool = CalendarTool(service=_fake_service(events))
    day = datetime(2026, 4, 14, 0, 0, tzinfo=UTC)
    slots = tool.find_free_time(date=day, duration_minutes=30)
    # Should have two slots: 09:00-10:00 and 10:30-22:00
    assert len(slots) == 2
    assert slots[0][1].hour == 10
    assert slots[1][0].hour == 10 and slots[1][0].minute == 30


def test_find_free_time_morning_hint() -> None:
    events = [
        {
            "id": "e1",
            "summary": "Standup",
            "start": {"dateTime": "2026-04-14T10:00:00+00:00"},
            "end": {"dateTime": "2026-04-14T10:30:00+00:00"},
        }
    ]
    tool = CalendarTool(service=_fake_service(events))
    day = datetime(2026, 4, 14, 0, 0, tzinfo=UTC)
    slots = tool.find_free_time(date=day, duration_minutes=30, time_hint="morning")
    # Morning window is 09:00-12:00, with 10:00-10:30 busy
    # Slots: 09:00-10:00 and 10:30-12:00
    assert len(slots) == 2
    assert slots[0][0].hour == 9
    assert slots[1][1].hour == 12


def test_find_free_time_no_slots_available() -> None:
    # Back-to-back meetings filling 09:00-22:00
    events = [
        {
            "id": "e1",
            "summary": "All day block",
            "start": {"dateTime": "2026-04-14T09:00:00+00:00"},
            "end": {"dateTime": "2026-04-14T22:00:00+00:00"},
        }
    ]
    tool = CalendarTool(service=_fake_service(events))
    day = datetime(2026, 4, 14, 0, 0, tzinfo=UTC)
    slots = tool.find_free_time(date=day, duration_minutes=30)
    assert slots == []


def test_find_free_time_overlapping_meetings_merged() -> None:
    events = [
        {
            "id": "e1",
            "summary": "Meeting A",
            "start": {"dateTime": "2026-04-14T10:00:00+00:00"},
            "end": {"dateTime": "2026-04-14T11:00:00+00:00"},
        },
        {
            "id": "e2",
            "summary": "Meeting B",
            "start": {"dateTime": "2026-04-14T10:30:00+00:00"},
            "end": {"dateTime": "2026-04-14T11:30:00+00:00"},
        },
    ]
    tool = CalendarTool(service=_fake_service(events))
    day = datetime(2026, 4, 14, 0, 0, tzinfo=UTC)
    slots = tool.find_free_time(date=day, duration_minutes=30)
    # Overlapping meetings merge to 10:00-11:30
    # Slots: 09:00-10:00 and 11:30-22:00
    assert len(slots) == 2
    assert slots[0][1].hour == 10
    assert slots[1][0].hour == 11 and slots[1][0].minute == 30
