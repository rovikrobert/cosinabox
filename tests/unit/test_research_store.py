from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cosinabox.memory import Memory

NOW = datetime(2026, 8, 20, tzinfo=UTC)


@pytest.fixture
def mem(tmp_path):
    return Memory(db_path=tmp_path / "test.db")


def test_signals_persist_and_count_per_week(mem):
    written = mem.save_research_signals(
        [
            {
                "headline": "H1",
                "source_url": "https://x/1",
                "entity": "Org Alpha",
                "why_it_matters": "w",
            },
            {
                "headline": "H2",
                "source_url": "https://x/2",
                "entity": "Org Beta",
                "why_it_matters": "w",
            },
        ],
        week_of="2026-08-17",
    )
    assert written == 2
    assert mem.research_signal_count(week_of="2026-08-17") == 2
    assert mem.research_signal_count(week_of="2026-08-10") == 0


def test_saving_the_same_url_twice_in_a_week_is_idempotent(mem):
    row = {"headline": "H", "source_url": "https://x/1", "entity": "E", "why_it_matters": "w"}
    mem.save_research_signals([row], week_of="2026-08-17")
    mem.save_research_signals([row], week_of="2026-08-17")
    assert mem.research_signal_count(week_of="2026-08-17") == 1


def test_malformed_signal_rows_are_skipped_not_fatal(mem):
    written = mem.save_research_signals(
        ["not a dict", {"headline": "ok", "source_url": "https://x/9"}, {}],
        week_of="2026-08-17",
    )
    # The string and the keyless dict are skipped; the usable row lands.
    assert written == 1


def test_dedup_round_trips(mem):
    mem.save_research_dedup([{"url": "https://x/1", "headline": "H1"}], week_of="2026-08-17")
    loaded = mem.load_research_dedup(now=NOW, ttl_days=30, cap=150)
    assert loaded == [{"url": "https://x/1", "headline": "H1", "week_of": "2026-08-17"}]


def test_dedup_entries_older_than_the_ttl_are_dropped(mem):
    old_week = (NOW - timedelta(days=60)).date().isoformat()
    mem.save_research_dedup([{"url": "https://old", "headline": "O"}], week_of=old_week)
    mem.save_research_dedup([{"url": "https://new", "headline": "N"}], week_of="2026-08-17")
    urls = [e["url"] for e in mem.load_research_dedup(now=NOW, ttl_days=30, cap=150)]
    assert urls == ["https://new"]


def test_dedup_respects_the_cap(mem):
    for n in range(10):
        mem.save_research_dedup(
            [{"url": f"https://x/{n}", "headline": str(n)}], week_of="2026-08-17"
        )
    assert len(mem.load_research_dedup(now=NOW, ttl_days=30, cap=4)) == 4
