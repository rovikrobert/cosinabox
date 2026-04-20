"""Commitment value types, enums, and exceptions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CommitmentStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


VALID_STATUSES: frozenset[str] = frozenset(s.value for s in CommitmentStatus)
VALID_SOURCES: frozenset[str] = frozenset({"chat", "email", "meeting", "manual"})
UPDATABLE_FIELDS: frozenset[str] = frozenset(
    {"status", "priority", "deadline", "description", "owner", "stakeholder", "workstream"}
)
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {CommitmentStatus.DONE.value, CommitmentStatus.CANCELLED.value}
)


class CommitmentNotFound(Exception):
    """Raised when a commitment ID does not exist."""


class CommitmentAlreadyClosed(Exception):
    """Raised when closing/dismissing a commitment already in a terminal state."""


class CommitmentNotClosed(Exception):
    """Raised when reopening a commitment that isn't in a terminal state."""


@dataclass
class Commitment:
    """Typed view over a commitments row. Returned by helpers that want a
    stable surface; the dict form is still available for prompt injection.
    """

    id: int
    title: str
    description: str | None
    owner: str
    status: str
    priority: int
    deadline: str | None
    source: str
    source_ref: str | None
    stakeholder: str | None
    workstream: str | None
    last_verdict: str | None
    last_verdict_at: str | None
    created_at: str
    updated_at: str
