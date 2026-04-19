# ruff: noqa: I001
"""Tests for event relevance allowlist in `is_prep_worthy`.

An allowlist (keywords + domains) narrows prep to events you care about —
stops pre-meeting prep from firing on tangential calendar items like a
pickup-group lunch or a renewal reminder with many attendees.

Without an allowlist, the blocklist-only behavior from PR #54 stays intact.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cosinabox.jobs._meeting_filter import is_prep_worthy
from cosinabox.tools.google.calendar import CalendarEvent


def _event(
    summary: str,
    attendees: list[str] | None = None,
) -> CalendarEvent:
    now = datetime.now(UTC)
    return CalendarEvent(
        id="e",
        summary=summary,
        start=now + timedelta(minutes=30),
        end=now + timedelta(minutes=60),
        attendees=attendees or ["a@x.com", "b@x.com"],
    )


# -- allowlist narrows: must match keyword OR domain --------------------------


def test_allowlist_keyword_match_is_prep_worthy() -> None:
    assert (
        is_prep_worthy(
            _event("NTU S-Lab research call"),
            relevance_keywords=["ntu", "edb"],
        )
        is True
    )


def test_allowlist_domain_match_is_prep_worthy() -> None:
    assert (
        is_prep_worthy(
            _event("Catch-up", attendees=["someone@sequoia.com"]),
            relevance_domains=["sequoia.com"],
        )
        is True
    )


def test_allowlist_no_match_is_skipped() -> None:
    """Event doesn't match keywords or domains → skip even with attendees."""
    assert (
        is_prep_worthy(
            _event("Birthday lunch", attendees=["friend@gmail.com"]),
            relevance_keywords=["ntu", "edb"],
            relevance_domains=["cantina.ai"],
        )
        is False
    )


def test_allowlist_keyword_case_insensitive() -> None:
    assert (
        is_prep_worthy(
            _event("Meeting with EDB team"),
            relevance_keywords=["edb"],
        )
        is True
    )


def test_allowlist_domain_case_insensitive_and_trailing_match() -> None:
    assert (
        is_prep_worthy(
            _event("Call", attendees=["Person@Cantina.AI"]),
            relevance_domains=["cantina.ai"],
        )
        is True
    )


# -- allowlist + blocklist interaction ----------------------------------------


def test_blocklist_still_applies_when_allowlist_set() -> None:
    """Solo 'Decompress' blocked even if kwlist is broad."""
    now = datetime.now(UTC)
    solo = CalendarEvent(
        id="e",
        summary="Decompress with NTU prep",
        start=now,
        end=now + timedelta(minutes=15),
        attendees=[],
    )
    assert (
        is_prep_worthy(
            solo,
            relevance_keywords=["ntu"],
        )
        is False
    )


def test_allowlist_doesnt_override_personal_pattern() -> None:
    """Personal block ('lunch') still wins over allowlist keyword match."""
    assert (
        is_prep_worthy(
            _event("NTU lunch catch-up"),  # has 'ntu' AND 'lunch'
            relevance_keywords=["ntu"],
        )
        is False
    )


# -- no allowlist: behavior unchanged -----------------------------------------


def test_no_allowlist_keeps_default_behavior() -> None:
    """Unrelated event with attendees still prep-worthy when no allowlist set."""
    assert is_prep_worthy(_event("Random sync")) is True


def test_empty_allowlist_tuple_same_as_no_allowlist() -> None:
    """Empty lists are explicitly 'no allowlist' — not 'reject everything'."""
    assert (
        is_prep_worthy(
            _event("Random sync"),
            relevance_keywords=[],
            relevance_domains=[],
        )
        is True
    )
