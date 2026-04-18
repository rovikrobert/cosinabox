"""Shared filter for calendar-driven jobs.

Inspired by cos-agent's ``_is_cantina_relevant`` (an allowlist of domains +
keywords for the maintainer's org). Here we ship the mechanism, not the
specific keywords — the OSS engine can't assume who matters to you.

The current contract is a *blocklist*:

1. Solo events (no attendees) are never prep-worthy — they're time blocks,
   not meetings.
2. Titles matching built-in personal-block patterns
   (``DEFAULT_PERSONAL_BLOCK_PATTERNS`` in ``defaults.py``) are skipped.
3. Per-job user ``skip_titles`` are honored in addition.

An allowlist extension (e.g., ``relevance_keywords`` in ``personality.md``)
is a follow-up; file an issue if you need it.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from cosinabox.defaults import DEFAULT_PERSONAL_BLOCK_PATTERNS


def is_prep_worthy(
    event: Any,
    *,
    skip_titles: Iterable[str] = (),
) -> bool:
    """Return True if ``event`` deserves agent-generated prep or debrief.

    ``event`` is expected to have ``summary: str`` and
    ``attendees: list[str]`` — the ``CalendarEvent`` shape. Duck-typed for
    test fakes.
    """
    attendees = getattr(event, "attendees", None) or []
    if len(attendees) == 0:
        return False

    summary = (getattr(event, "summary", "") or "").lower()
    if not summary:
        # Untitled event with attendees is weird but not disqualifying on
        # its own — return True and let downstream handle it.
        return True

    for pattern in DEFAULT_PERSONAL_BLOCK_PATTERNS:
        if pattern in summary:
            return False

    return not any(skip and skip.lower() in summary for skip in skip_titles)
