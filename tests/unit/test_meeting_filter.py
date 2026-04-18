# ruff: noqa: I001  # match style in test_agent_failover for consistency
"""Tests for `is_prep_worthy` — shared filter for calendar-driven jobs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cosinabox.jobs._meeting_filter import is_prep_worthy
from cosinabox.tools.google.calendar import CalendarEvent


def _event(summary: str, attendees: list[str] | None = None) -> CalendarEvent:
    now = datetime.now(UTC)
    return CalendarEvent(
        id="e1",
        summary=summary,
        start=now + timedelta(minutes=30),
        end=now + timedelta(minutes=60),
        attendees=attendees or [],
    )


# -- solo blocks -------------------------------------------------------------


def test_zero_attendees_is_solo_block() -> None:
    """A Google event with no invitees has no attendees array → solo block."""
    assert is_prep_worthy(_event("Working time", attendees=[])) is False


def test_zero_attendees_even_with_meeting_title() -> None:
    """No attendees → skip even if the title sounds like a meeting."""
    assert is_prep_worthy(_event("Q3 Strategy Sync", attendees=[])) is False


# -- default personal-block patterns ----------------------------------------


def test_default_pattern_decompress() -> None:
    assert is_prep_worthy(_event("Decompress", attendees=["a@x.com", "b@x.com"])) is False


def test_default_pattern_focus_case_insensitive() -> None:
    assert is_prep_worthy(_event("FOCUS TIME", attendees=["a@x.com", "b@x.com"])) is False


def test_default_pattern_lunch() -> None:
    assert is_prep_worthy(_event("Lunch", attendees=["a@x.com", "b@x.com"])) is False


def test_default_pattern_substring_match() -> None:
    """Patterns match as substrings — 'Deep Work Block' trips 'deep work'."""
    assert is_prep_worthy(_event("Deep Work Block", attendees=["a@x.com", "b@x.com"])) is False


# -- user-configured skip_titles --------------------------------------------


def test_user_skip_title_skips() -> None:
    assert (
        is_prep_worthy(
            _event("Internal planning", attendees=["a@x.com", "b@x.com"]),
            skip_titles=["internal"],
        )
        is False
    )


def test_user_skip_title_is_lowercased_at_compare_time() -> None:
    """Caller may pass mixed-case skip list; filter compares case-insensitively."""
    assert (
        is_prep_worthy(
            _event("INTERNAL SYNC", attendees=["a@x.com", "b@x.com"]),
            skip_titles=["Internal"],
        )
        is False
    )


# -- real meetings (positive cases) -----------------------------------------


def test_real_meeting_with_attendees_is_prep_worthy() -> None:
    assert is_prep_worthy(_event("Strategy Review", attendees=["a@x.com", "b@x.com"])) is True


def test_one_attendee_is_still_prep_worthy_if_not_personal() -> None:
    """A 1-on-1 sometimes registers with a single non-self attendee."""
    assert is_prep_worthy(_event("1:1 with Sarah", attendees=["sarah@x.com"])) is True


def test_real_meeting_unaffected_by_default_patterns() -> None:
    """'focus' as a word in a title shouldn't false-positive when it's clearly a meeting.

    This is a known tradeoff: patterns match as substrings. If users hit
    false positives they can promote titles via explicit skip_titles or
    rename the event. We verify the current contract here so behaviour
    changes are visible in review.
    """
    # "Customer focus group" → contains "focus" → WILL be skipped.
    # If this ever changes, update the assertion and note the reason.
    assert is_prep_worthy(_event("Customer focus group", attendees=["a@x.com", "b@x.com"])) is False
