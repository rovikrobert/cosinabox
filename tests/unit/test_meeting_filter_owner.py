# ruff: noqa: I001
"""The owner's own address must not make an event prep-worthy.

Calendar events you create for yourself list you as the sole attendee, so
`len(attendees) == 0` never fires for them. If your own domain is in
`event_relevance.domains` — the common case, since that is the domain you
work at — every personal appointment matches the allowlist and earns a
full agent-generated prep.

Found in the legacy implementation, where a recurring language lesson on
the maintainer's own calendar produced a stakeholder brief every week.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cosinabox.jobs._meeting_filter import is_prep_worthy
from cosinabox.tools.google.calendar import CalendarEvent


def _event(summary: str, attendees: list[str]) -> CalendarEvent:
    now = datetime.now(UTC)
    return CalendarEvent(
        id="e",
        summary=summary,
        start=now + timedelta(minutes=30),
        end=now + timedelta(minutes=60),
        attendees=attendees,
    )


def test_solo_event_with_only_the_owner_is_not_prep_worthy() -> None:
    """The real shape: a lesson booked on your own calendar."""
    assert (
        is_prep_worthy(
            _event("Language lesson - Qiu.xia Z.", ["me@acme.com"]),
            relevance_domains=["acme.com"],
            owner_emails=["me@acme.com"],
        )
        is False
    )


def test_solo_owner_event_is_not_prep_worthy_without_an_allowlist() -> None:
    """A solo event is a time block whether or not an allowlist is set."""
    assert (
        is_prep_worthy(
            _event("Dentist", ["me@acme.com"]),
            owner_emails=["me@acme.com"],
        )
        is False
    )


def test_owner_matching_is_case_insensitive() -> None:
    assert (
        is_prep_worthy(
            _event("Dentist", ["Me@Acme.com"]),
            owner_emails=["me@acme.com"],
        )
        is False
    )


def test_owner_plus_a_real_counterparty_is_still_prep_worthy() -> None:
    assert (
        is_prep_worthy(
            _event("Partnership sync", ["me@acme.com", "them@acme.com"]),
            relevance_domains=["acme.com"],
            owner_emails=["me@acme.com"],
        )
        is True
    )


def test_counterparty_alone_still_matches_the_domain_allowlist() -> None:
    assert (
        is_prep_worthy(
            _event("Intro call", ["them@acme.com"]),
            relevance_domains=["acme.com"],
            owner_emails=["me@acme.com"],
        )
        is True
    )


def test_solo_owner_event_is_skipped_even_with_a_keyword_match() -> None:
    """Owner-only means solo, and this module's contract is that solo events
    are never prep-worthy — they're time blocks, not meetings. A keyword does
    not resurrect a bare block today, and it must not resurrect this one
    either; the two cases stay identical.
    """
    assert (
        is_prep_worthy(
            _event("Prep for EDB submission", ["me@acme.com"]),
            relevance_keywords=["edb"],
            owner_emails=["me@acme.com"],
        )
        is False
    )


def test_no_owner_emails_configured_keeps_previous_behavior() -> None:
    """Owner exclusion is opt-in; omitting it must not change anything."""
    assert (
        is_prep_worthy(
            _event("Language lesson", ["me@acme.com"]),
            relevance_domains=["acme.com"],
        )
        is True
    )
