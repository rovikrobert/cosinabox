"""Scheduling context — typed container for all scheduling dependencies.

Phase B introduces ``SchedulingContext`` as the single object threaded through
every coordinator entry point.  It owns the DB handle, owner profile, calendar
provider, and all integration adapters that scheduling needs.

The ``CalendarProvider`` protocol defines the narrow contract the scheduling
engine requires from any calendar backend.  The Google Calendar adapter
(``GoogleCalendarProvider``) wraps the existing ``CalendarTool`` behind this
protocol; tests use ``FakeCalendarProvider``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Value types returned by the CalendarProvider protocol
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BusyInterval:
    """A time range during which the owner's calendar is busy.

    ``source_event_id`` is optional metadata — populated by the Google
    adapter, ``None`` for fake/test providers.
    """

    start: datetime
    end: datetime
    source_event_id: str | None = None


@dataclass(frozen=True)
class CreatedEvent:
    """Result of creating a calendar event via the provider."""

    event_id: str
    title: str
    start: datetime
    end: datetime
    attendees: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CalendarProvider protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class CalendarProvider(Protocol):
    """Narrow protocol for calendar operations the scheduling engine needs.

    Implementations:
        - ``GoogleCalendarProvider`` — wraps ``CalendarTool.list_events``
          and ``CalendarTool.create_event``.
        - ``FakeCalendarProvider`` — test double with configurable intervals.

    Timezone handling:
        - ``list_busy_intervals`` returns timezone-aware datetimes.
        - All-day events are treated as full-day busy (00:00–24:00 UTC).
    """

    def list_busy_intervals(
        self,
        *,
        start: datetime,
        end: datetime,
        timezone: str,
    ) -> list[BusyInterval]: ...

    def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        attendees: list[str],
        description: str | None = None,
    ) -> CreatedEvent: ...


# ---------------------------------------------------------------------------
# Owner profile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OwnerProfile:
    """The scheduling host's identity — threaded once, not per-call."""

    name: str
    timezone: str
    email: str | None = None


# ---------------------------------------------------------------------------
# SchedulingContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchedulingContext:
    """Frozen context object built once at app-wire time.

    Passed to every coordinator entry point. Use ``replace()`` to create
    variants for testing::

        ctx = SchedulingContext(db=mem, owner=owner)
        test_ctx = ctx.replace(calendar=FakeCalendarProvider(...))
    """

    db: Any  # Memory instance
    owner: OwnerProfile

    # Optional integrations — None means "not configured".
    calendar: CalendarProvider | None = None
    gmail: Any | None = None
    bot: Any | None = None  # SyncSchedulingBotAdapter or None

    anthropic_client: Any | None = None
    cost_tracker: Any | None = None

    scoring_config: Any | None = None  # ScoringConfig or None

    def replace(self, **changes: Any) -> SchedulingContext:
        """Return a shallow copy with the given fields replaced."""
        return replace(self, **changes)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_from_integrations(
    *,
    db: Any,
    owner_name: str,
    owner_timezone: str,
    owner_email: str | None = None,
    calendar: CalendarProvider | None = None,
    gmail: Any | None = None,
    bot: Any | None = None,
    anthropic_client: Any | None = None,
    cost_tracker: Any | None = None,
    scoring_config: Any | None = None,
) -> SchedulingContext:
    """Construct a ``SchedulingContext`` from raw integration objects.

    This is the single construction site — ``app/_core.py`` calls this once
    and threads the result everywhere.
    """
    owner = OwnerProfile(
        name=owner_name,
        timezone=owner_timezone,
        email=owner_email,
    )
    return SchedulingContext(
        db=db,
        owner=owner,
        calendar=calendar,
        gmail=gmail,
        bot=bot,
        anthropic_client=anthropic_client,
        cost_tracker=cost_tracker,
        scoring_config=scoring_config,
    )


__all__ = [
    "BusyInterval",
    "CalendarProvider",
    "CreatedEvent",
    "OwnerProfile",
    "SchedulingContext",
    "build_from_integrations",
]
