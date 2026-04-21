"""Internal utilities shared across the memory/ and commitments/ modules."""

from __future__ import annotations

from datetime import UTC, datetime


def now_iso() -> str:
    """Return the current UTC instant as an ISO-8601 string.

    Shared by history/commitment writes so the timestamp format stays
    consistent across tables.
    """
    return datetime.now(UTC).isoformat()
