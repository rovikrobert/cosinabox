"""Stage 1: gather candidate items from search and feeds.

Runs outside any model call — this is a plain data pipeline whose output
becomes the synthesis prompt.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Protocol

from cosinabox import defaults
from cosinabox.research.config import Query, ResearchConfig

logger = logging.getLogger(__name__)

# Items from feeds are untargeted, so they must earn their place by mentioning
# a tracked term. Items from queries are relevant by construction.
FEED_GROUP = "feed"
_FEED_PRIORITY = 20_000


class SearchBackend(Protocol):
    def __call__(
        self,
        query: str,
        *,
        country: str,
        topic: str,
        time_range: str | None,
        max_results: int,
    ) -> list[dict[str, Any]]: ...


class FeedReader(Protocol):
    def __call__(self, feeds: tuple[str, ...]) -> list[dict[str, Any]]: ...


@dataclass
class CollectionResult:
    items: list[dict[str, Any]]
    search_failed: bool
    counts: dict[str, int] = field(default_factory=dict)


def dedup_by_url(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop repeat URLs, keeping the first occurrence. Urlless items are noise."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        url = item.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(item)
    return out


def filter_by_tracked_terms(items: list[dict[str, Any]], terms: set[str]) -> list[dict[str, Any]]:
    """Keep feed items only when they mention a tracked term.

    Everything else passes through: it arrived via a targeted query. A single
    high-volume feed otherwise floods the candidate set and displaces the
    results the user actually asked for.
    """
    out: list[dict[str, Any]] = []
    for item in items:
        if item.get("priority_group") != FEED_GROUP:
            out.append(item)
            continue
        haystack = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
        if any(term in haystack for term in terms):
            out.append(item)
    return out


def cap_by_priority(items: list[dict[str, Any]], *, max_results: int) -> list[dict[str, Any]]:
    """Trim to `max_results`, dropping the highest priority numbers first.

    Sorting before slicing is the whole point: slicing in append order is what
    let one group's results be cut entirely in the legacy implementation.
    Python's sort is stable, so order within a priority level is preserved.
    """
    ordered = sorted(items, key=lambda i: i.get("priority", _FEED_PRIORITY))
    return ordered[:max_results]


def _run_query(search: SearchBackend, q: Query) -> list[dict[str, Any]]:
    items = search(
        q.text,
        country=q.search.country,
        topic=q.search.topic,
        time_range=q.search.time_range,
        max_results=q.search.results_per_query,
    )
    for item in items:
        item["priority"] = q.priority
        item["priority_group"] = q.group
    return items


def collect(
    cfg: ResearchConfig,
    *,
    search: SearchBackend,
    feed_reader: FeedReader | None,
    max_workers: int = defaults.RESEARCH_MAX_WORKERS,
) -> CollectionResult:
    """Run every configured query plus the feeds, then dedup, filter and cap.

    A single failing query is logged and skipped. Only *every* query failing
    counts as `search_failed` — synthesizing from feeds alone would produce a
    digest that looks fine and silently omits the tracked entities.
    """
    queries = cfg.queries()
    raw: list[dict[str, Any]] = []
    failures = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run_query, search, q): q for q in queries}
        for future, q in futures.items():
            try:
                raw.extend(future.result())
            except Exception as exc:
                failures += 1
                logger.warning("Research query %r failed: %s", q.text, exc)

    search_failed = bool(queries) and failures == len(queries)
    if search_failed:
        logger.error("Aborting collection: all %d search queries failed", len(queries))
        return CollectionResult(items=[], search_failed=True, counts={"raw": 0})

    if feed_reader and cfg.feeds:
        try:
            for item in feed_reader(cfg.feeds):
                item["priority"] = _FEED_PRIORITY
                item["priority_group"] = FEED_GROUP
                raw.append(item)
        except Exception as exc:
            # Feeds are supplementary; losing them degrades the digest but
            # does not invalidate it.
            logger.warning("Feed collection failed: %s", exc)

    deduped = dedup_by_url(raw)
    filtered = filter_by_tracked_terms(deduped, cfg.tracked_terms())
    capped = cap_by_priority(filtered, max_results=defaults.RESEARCH_MAX_CANDIDATES)

    counts = {
        "raw": len(raw),
        "deduped": len(deduped),
        "filtered": len(filtered),
        "capped": len(capped),
    }
    logger.info(
        "Research collection: %d raw -> %d deduped -> %d filtered -> %d capped",
        counts["raw"],
        counts["deduped"],
        counts["filtered"],
        counts["capped"],
    )
    return CollectionResult(items=capped, search_failed=False, counts=counts)
