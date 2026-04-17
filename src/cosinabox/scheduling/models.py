"""Scheduling data models — dataclasses + state enum.

Ported from cos-agent/src/scheduling/models.py, no algorithmic changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class SchedulingStatus(StrEnum):
    """Status values for a scheduling request state machine."""

    PROPOSING = "proposing"
    OWNER_REVIEW = "owner_review"
    POLLING = "polling"
    CONVERGED = "converged"
    BOOKED = "booked"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    BACKCHANNEL = "backchannel"


class SchedulingStateError(Exception):
    """Raised when a DB integrity constraint is violated (bad status, FK, etc.)."""


@dataclass
class Participant:
    """A person involved in a scheduling request."""

    name: str
    email: str | None = None
    telegram_id: str | None = None
    timezone: str = "UTC"
    channel: str = "gmail"  # "telegram" | "gmail"
    db_id: int | None = None  # set after DB insert
    status: str = "pending"


@dataclass
class TimeSlot:
    """A candidate meeting time slot with scoring metadata."""

    start_time: datetime  # UTC
    end_time: datetime  # UTC
    score: float = 0.0
    requires_move: str | None = None  # calendar event_id, or None
    move_approved: bool = False
    db_id: int | None = None  # set after DB insert


@dataclass
class SchedulingRequest:
    """A group scheduling request."""

    id: str
    title: str
    duration_minutes: int
    participants: list[Participant] = field(default_factory=list)
    date_range_start: date = field(default_factory=date.today)
    date_range_end: date = field(default_factory=date.today)
    status: str = SchedulingStatus.PROPOSING.value
    preferred_timezone: str = "UTC"
    notes: str | None = None
    slots: list[TimeSlot] = field(default_factory=list)
    booked_event_id: str | None = None
