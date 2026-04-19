"""Shared filter for calendar-driven jobs.

Inspired by cos-agent's ``_is_cantina_relevant`` (an allowlist of domains +
keywords for the maintainer's org). Here the mechanism is generic — the
OSS engine doesn't assume who matters to you, but lets you declare it.

The contract is a *blocklist first, allowlist second*:

1. Solo events (no attendees) are never prep-worthy — they're time blocks,
   not meetings.
2. Titles matching built-in personal-block patterns
   (``DEFAULT_PERSONAL_BLOCK_PATTERNS`` in ``defaults.py``) are skipped.
3. Per-job user ``skip_titles`` are honored in addition.
4. **If** ``relevance_keywords`` or ``relevance_domains`` is non-empty, the
   event must also match at least one of them (title contains keyword, OR
   any attendee email ends with a listed domain). Empty/omitted = no
   narrowing; default blocklist-only behavior.

Callers read the allowlist from ``personality.md`` frontmatter
(``event_relevance.keywords`` + ``event_relevance.domains``) and pass it
through.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from cosinabox.defaults import DEFAULT_PERSONAL_BLOCK_PATTERNS


def is_prep_worthy(
    event: Any,
    *,
    skip_titles: Iterable[str] = (),
    relevance_keywords: Iterable[str] = (),
    relevance_domains: Iterable[str] = (),
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

    if any(skip and skip.lower() in summary for skip in skip_titles):
        return False

    # Allowlist narrowing. Only applies if either list is non-empty — so
    # users who don't set an allowlist keep the blocklist-only behavior.
    keywords = [k.lower() for k in relevance_keywords if k]
    domains = [d.lower().lstrip("@") for d in relevance_domains if d]
    if keywords or domains:
        kw_match = any(k in summary for k in keywords)
        domain_match = any(
            a.lower().endswith("@" + d) or a.lower().endswith("." + d) or a.lower().endswith(d)
            for a in attendees
            for d in domains
        )
        if not (kw_match or domain_match):
            return False

    return True
