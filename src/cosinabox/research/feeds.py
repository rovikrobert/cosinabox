"""RSS/Atom reading for the research digest (optional dep: cosinabox[research])."""
# mypy: disable-error-code="import-untyped"

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

try:
    import feedparser
except ImportError as e:  # pragma: no cover - exercised by the extras guard
    raise ImportError(
        "cosinabox[research] extra is required. Run: pip install 'cosinabox[research]'"
    ) from e

from cosinabox import defaults

logger = logging.getLogger(__name__)


def read_feeds(
    feeds: tuple[str, ...],
    *,
    now: datetime | None = None,
    max_age_days: int = defaults.RESEARCH_FEED_MAX_AGE_DAYS,
) -> list[dict[str, Any]]:
    """Fetch each feed and return entries published within the window.

    One unreachable feed must not cost the others, so failures are logged per
    feed. Entries with no parseable date are kept: we cannot prove they are
    stale, and the tracked-term filter plus the priority cap downstream keep
    them from dominating.
    """
    now = now or datetime.now(UTC)
    cutoff = (now - timedelta(days=max_age_days)).date()
    out: list[dict[str, Any]] = []

    for url in feeds:
        try:
            parsed = feedparser.parse(url)
        except Exception as exc:
            logger.warning("Feed %s failed: %s", url, exc)
            continue

        for entry in getattr(parsed, "entries", []) or []:
            published = ""
            stamp = getattr(entry, "published_parsed", None)
            if stamp:
                entry_date: date | None
                try:
                    # Index explicitly rather than unpacking stamp[:6]: only
                    # the date is compared against the cutoff, and an
                    # unbounded unpack can collide with the tzinfo kwarg.
                    entry_date = datetime(stamp[0], stamp[1], stamp[2], tzinfo=UTC).date()
                except (IndexError, TypeError, ValueError):
                    entry_date = None
                if entry_date is not None:
                    if entry_date < cutoff:
                        continue
                    published = entry_date.isoformat()

            link = getattr(entry, "link", "") or ""
            if not link:
                continue
            out.append(
                {
                    "title": getattr(entry, "title", "") or "",
                    "url": link,
                    "snippet": getattr(entry, "summary", "") or "",
                    "published": published,
                    "source": urlparse(link).netloc,
                }
            )
    return out
