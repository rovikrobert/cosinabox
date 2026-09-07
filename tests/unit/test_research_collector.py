from __future__ import annotations

from typing import Any

from cosinabox.research.collector import (
    cap_by_priority,
    collect,
    dedup_by_url,
    filter_by_tracked_terms,
)
from cosinabox.research.config import Entity, Group, ResearchConfig, SearchSpec


def _cfg() -> ResearchConfig:
    return ResearchConfig(
        groups=(
            Group(
                name="high",
                priority=0,
                search=SearchSpec(topic="news", time_range="week"),
                entities=(Entity(name="Org Alpha", aliases=("OrgA",), queries=("qa",)),),
            ),
            Group(
                name="low",
                priority=5,
                search=SearchSpec(),
                entities=(Entity(name="Org Beta", queries=("qb1", "qb2")),),
            ),
        ),
        feeds=(),
        field_queries=(),
    )


class _FakeSearch:
    """Returns one result per query, tagged so assertions can trace it."""

    def __init__(self, *, fail_on: set[str] | None = None) -> None:
        self.fail_on = fail_on or set()
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self, query: str, *, country: str, topic: str, time_range: str | None, max_results: int
    ) -> list[dict[str, Any]]:
        self.calls.append({"query": query, "topic": topic, "time_range": time_range})
        if query in self.fail_on:
            raise RuntimeError("boom")
        return [{"title": f"t-{query}", "url": f"https://x/{query}", "snippet": "", "source": "x"}]


def test_dedup_keeps_first_occurrence():
    items = [
        {"url": "https://a", "title": "first"},
        {"url": "https://a", "title": "second"},
        {"url": "https://b", "title": "third"},
        {"url": "", "title": "no url"},
    ]
    assert [i["title"] for i in dedup_by_url(items)] == ["first", "third"]


def test_feed_items_without_a_tracked_term_are_dropped():
    items = [
        {"url": "1", "title": "Org Alpha news", "snippet": "", "priority_group": "feed"},
        {"url": "2", "title": "unrelated paper", "snippet": "", "priority_group": "feed"},
        {"url": "3", "title": "unrelated", "snippet": "", "priority_group": "high"},
    ]
    kept = filter_by_tracked_terms(items, {"org alpha"})
    # Feed item 2 is dropped; the non-feed item passes untouched because it
    # came from a targeted query and is relevant by construction.
    assert [i["url"] for i in kept] == ["1", "3"]


def test_cap_keeps_lower_priority_numbers_first():
    items = [{"url": str(n), "priority": 5} for n in range(3)]
    items += [{"url": f"h{n}", "priority": 0} for n in range(3)]
    capped = cap_by_priority(items, max_results=3)
    assert [i["url"] for i in capped] == ["h0", "h1", "h2"]


def test_collect_runs_every_query_with_its_group_search_spec():
    search = _FakeSearch()
    result = collect(_cfg(), search=search, feed_reader=None, max_workers=2)

    assert result.search_failed is False
    assert sorted(c["query"] for c in search.calls) == ["qa", "qb1", "qb2"]
    news = [c for c in search.calls if c["query"] == "qa"][0]
    assert (news["topic"], news["time_range"]) == ("news", "week")
    general = [c for c in search.calls if c["query"] == "qb1"][0]
    assert (general["topic"], general["time_range"]) == ("general", None)
    assert result.counts["raw"] == 3


def test_collect_survives_individual_query_failures():
    search = _FakeSearch(fail_on={"qb1"})
    result = collect(_cfg(), search=search, feed_reader=None, max_workers=2)
    # One query died; the other two still produced results.
    assert result.search_failed is False
    assert result.counts["raw"] == 2


def test_collect_reports_total_search_failure():
    search = _FakeSearch(fail_on={"qa", "qb1", "qb2"})
    result = collect(_cfg(), search=search, feed_reader=None, max_workers=2)
    assert result.search_failed is True
    assert result.items == []


def test_feed_failure_does_not_abort_collection():
    def _bad_reader(feeds: tuple[str, ...]) -> list[dict[str, Any]]:
        raise RuntimeError("feed down")

    search = _FakeSearch()
    result = collect(_cfg(), search=search, feed_reader=_bad_reader, max_workers=2)
    assert result.search_failed is False
    assert result.counts["raw"] == 3
