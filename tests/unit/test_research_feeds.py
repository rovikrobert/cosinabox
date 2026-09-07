from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from cosinabox.research.feeds import read_feeds

NOW = datetime(2026, 8, 20, tzinfo=UTC)


def _entry(title: str, link: str, *, day: int) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        link=link,
        summary=f"summary of {title}",
        published_parsed=(2026, 8, day, 0, 0, 0, 0, 0, 0),
    )


def test_recent_entries_are_returned_with_normalised_keys(monkeypatch):
    monkeypatch.setattr(
        "cosinabox.research.feeds.feedparser.parse",
        lambda url: SimpleNamespace(entries=[_entry("Fresh", "https://x/1", day=18)]),
    )
    items = read_feeds(("https://f",), now=NOW, max_age_days=7)
    assert items == [
        {
            "title": "Fresh",
            "url": "https://x/1",
            "snippet": "summary of Fresh",
            "published": "2026-08-18",
            "source": "x",
        }
    ]


def test_entries_older_than_the_window_are_dropped(monkeypatch):
    monkeypatch.setattr(
        "cosinabox.research.feeds.feedparser.parse",
        lambda url: SimpleNamespace(entries=[_entry("Stale", "https://x/2", day=1)]),
    )
    assert read_feeds(("https://f",), now=NOW, max_age_days=7) == []


def test_one_bad_feed_does_not_lose_the_others(monkeypatch):
    def _parse(url: str):
        if "bad" in url:
            raise RuntimeError("unreachable")
        return SimpleNamespace(entries=[_entry("Good", "https://x/3", day=19)])

    monkeypatch.setattr("cosinabox.research.feeds.feedparser.parse", _parse)
    items = read_feeds(("https://bad", "https://good"), now=NOW, max_age_days=7)
    assert [i["title"] for i in items] == ["Good"]


def test_entry_without_a_date_is_kept(monkeypatch):
    entry = SimpleNamespace(title="Undated", link="https://x/4", summary="s", published_parsed=None)
    monkeypatch.setattr(
        "cosinabox.research.feeds.feedparser.parse",
        lambda url: SimpleNamespace(entries=[entry]),
    )
    items = read_feeds(("https://f",), now=NOW, max_age_days=7)
    # No date means we cannot prove it is stale; the tracked-term filter and
    # the priority cap are the downstream guards.
    assert [i["title"] for i in items] == ["Undated"]
    assert items[0]["published"] == ""
