"""Unit tests for SchedulingContext, CalendarProvider protocol, and helpers."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from cosinabox.scheduling.context import (
    BusyInterval,
    CalendarProvider,
    CreatedEvent,
    OwnerProfile,
    SchedulingContext,
    build_from_integrations,
)

# ---------------------------------------------------------------------------
# Fake provider for protocol conformance tests
# ---------------------------------------------------------------------------


class FakeCalendarProvider:
    """Minimal CalendarProvider implementation for tests."""

    def __init__(
        self,
        busy: list[BusyInterval] | None = None,
        created: CreatedEvent | None = None,
    ) -> None:
        self._busy = busy or []
        self._created = created
        self.calls: list[str] = []

    def list_busy_intervals(
        self,
        *,
        start: datetime,
        end: datetime,
        timezone: str,
    ) -> list[BusyInterval]:
        self.calls.append("list_busy_intervals")
        return self._busy

    def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        attendees: list[str],
        description: str | None = None,
    ) -> CreatedEvent:
        self.calls.append("create_event")
        if self._created is not None:
            return self._created
        return CreatedEvent(
            event_id="fake-1",
            title=title,
            start=start,
            end=end,
            attendees=attendees,
        )


# ---------------------------------------------------------------------------
# BusyInterval / CreatedEvent
# ---------------------------------------------------------------------------


class TestBusyInterval:
    def test_frozen(self):
        bi = BusyInterval(
            start=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
            end=datetime(2026, 5, 4, 10, 0, tzinfo=UTC),
        )
        with pytest.raises(FrozenInstanceError):
            bi.start = datetime(2026, 5, 4, 11, 0, tzinfo=UTC)  # type: ignore[misc]

    def test_source_event_id_default_none(self):
        bi = BusyInterval(
            start=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
            end=datetime(2026, 5, 4, 10, 0, tzinfo=UTC),
        )
        assert bi.source_event_id is None

    def test_source_event_id_populated(self):
        bi = BusyInterval(
            start=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
            end=datetime(2026, 5, 4, 10, 0, tzinfo=UTC),
            source_event_id="evt-123",
        )
        assert bi.source_event_id == "evt-123"


class TestCreatedEvent:
    def test_frozen(self):
        ce = CreatedEvent(
            event_id="e1",
            title="Test",
            start=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
            end=datetime(2026, 5, 4, 10, 0, tzinfo=UTC),
        )
        with pytest.raises(FrozenInstanceError):
            ce.event_id = "e2"  # type: ignore[misc]

    def test_attendees_default_empty(self):
        ce = CreatedEvent(
            event_id="e1",
            title="Test",
            start=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
            end=datetime(2026, 5, 4, 10, 0, tzinfo=UTC),
        )
        assert ce.attendees == []


# ---------------------------------------------------------------------------
# OwnerProfile
# ---------------------------------------------------------------------------


class TestOwnerProfile:
    def test_frozen(self):
        op = OwnerProfile(name="Host", timezone="UTC")
        with pytest.raises(FrozenInstanceError):
            op.name = "Other"  # type: ignore[misc]

    def test_email_default_none(self):
        op = OwnerProfile(name="Host", timezone="UTC")
        assert op.email is None

    def test_email_populated(self):
        op = OwnerProfile(name="Host", timezone="UTC", email="host@x.com")
        assert op.email == "host@x.com"


# ---------------------------------------------------------------------------
# CalendarProvider protocol conformance
# ---------------------------------------------------------------------------


class TestCalendarProviderProtocol:
    def test_fake_is_instance(self):
        """FakeCalendarProvider satisfies the CalendarProvider protocol."""
        provider = FakeCalendarProvider()
        assert isinstance(provider, CalendarProvider)

    def test_list_busy_intervals(self):
        intervals = [
            BusyInterval(
                start=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
                end=datetime(2026, 5, 4, 10, 0, tzinfo=UTC),
            ),
        ]
        provider = FakeCalendarProvider(busy=intervals)
        result = provider.list_busy_intervals(
            start=datetime(2026, 5, 4, 0, 0, tzinfo=UTC),
            end=datetime(2026, 5, 5, 0, 0, tzinfo=UTC),
            timezone="UTC",
        )
        assert result == intervals
        assert provider.calls == ["list_busy_intervals"]

    def test_create_event(self):
        provider = FakeCalendarProvider()
        result = provider.create_event(
            title="Kickoff",
            start=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
            end=datetime(2026, 5, 4, 10, 0, tzinfo=UTC),
            attendees=["alice@x.com"],
        )
        assert result.event_id == "fake-1"
        assert result.title == "Kickoff"
        assert provider.calls == ["create_event"]


# ---------------------------------------------------------------------------
# SchedulingContext
# ---------------------------------------------------------------------------


class TestSchedulingContext:
    def test_construction_minimal(self, tmp_path):
        from cosinabox.memory import Memory

        mem = Memory(db_path=tmp_path / "test.db")
        owner = OwnerProfile(name="Host", timezone="UTC")
        ctx = SchedulingContext(db=mem, owner=owner)
        assert ctx.db is mem
        assert ctx.owner is owner
        assert ctx.calendar is None
        assert ctx.gmail is None
        assert ctx.bot is None
        assert ctx.anthropic_client is None
        assert ctx.cost_tracker is None
        assert ctx.scoring_config is None

    def test_frozen(self, tmp_path):
        from cosinabox.memory import Memory

        mem = Memory(db_path=tmp_path / "test.db")
        owner = OwnerProfile(name="Host", timezone="UTC")
        ctx = SchedulingContext(db=mem, owner=owner)
        with pytest.raises(FrozenInstanceError):
            ctx.db = None  # type: ignore[misc]

    def test_replace(self, tmp_path):
        from cosinabox.memory import Memory

        mem = Memory(db_path=tmp_path / "test.db")
        owner = OwnerProfile(name="Host", timezone="UTC")
        ctx = SchedulingContext(db=mem, owner=owner)
        provider = FakeCalendarProvider()
        ctx2 = ctx.replace(calendar=provider)
        assert ctx2.calendar is provider
        assert ctx2.db is mem  # unchanged
        assert ctx.calendar is None  # original unchanged

    def test_none_calendar_is_valid(self, tmp_path):
        """ctx.calendar=None is the 'no calendar configured' state."""
        from cosinabox.memory import Memory

        mem = Memory(db_path=tmp_path / "test.db")
        owner = OwnerProfile(name="Host", timezone="UTC")
        ctx = SchedulingContext(db=mem, owner=owner, calendar=None)
        assert ctx.calendar is None


# ---------------------------------------------------------------------------
# build_from_integrations
# ---------------------------------------------------------------------------


class TestBuildFromIntegrations:
    def test_minimal(self, tmp_path):
        from cosinabox.memory import Memory

        mem = Memory(db_path=tmp_path / "test.db")
        ctx = build_from_integrations(
            db=mem,
            owner_name="Host",
            owner_timezone="Asia/Singapore",
        )
        assert ctx.owner.name == "Host"
        assert ctx.owner.timezone == "Asia/Singapore"
        assert ctx.owner.email is None
        assert ctx.calendar is None

    def test_with_all_integrations(self, tmp_path):
        from cosinabox.memory import Memory

        mem = Memory(db_path=tmp_path / "test.db")
        provider = FakeCalendarProvider()
        gmail_mock = object()
        bot_mock = object()
        anthropic_mock = object()
        cost_mock = object()

        ctx = build_from_integrations(
            db=mem,
            owner_name="Host",
            owner_timezone="UTC",
            owner_email="host@x.com",
            calendar=provider,
            gmail=gmail_mock,
            bot=bot_mock,
            anthropic_client=anthropic_mock,
            cost_tracker=cost_mock,
        )
        assert ctx.calendar is provider
        assert ctx.gmail is gmail_mock
        assert ctx.bot is bot_mock
        assert ctx.anthropic_client is anthropic_mock
        assert ctx.cost_tracker is cost_mock
        assert ctx.owner.email == "host@x.com"
