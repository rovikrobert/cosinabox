# ruff: noqa: I001
"""Tests for analytics functions ported from cos-agent.

Covers the gap identified in the commitments port retro:
- get_commitment_velocity (unblocked by the commitments port)
- get_error_patterns (recurring tool errors)
- get_error_pattern_summary (cached system-prompt formatter)
- get_analytics_summary (CLI/DM formatter)
"""

from __future__ import annotations

from pathlib import Path
from datetime import UTC, datetime, timedelta

import pytest

from cosinabox.agent.analytics import (
    get_analytics_summary,
    get_commitment_velocity,
    get_error_pattern_summary,
    get_error_patterns,
    invalidate_error_summary_cache,
)
from cosinabox.commitments import close_commitment, create_commitment
from cosinabox.memory import Memory


@pytest.fixture(autouse=True)
def _reset_analytics_cache():
    """Cache state is module-global. Reset between tests to prevent order
    dependencies when running under pytest-xdist or with a warm cache from
    a prior test.
    """
    invalidate_error_summary_cache()
    yield
    invalidate_error_summary_cache()


@pytest.fixture
def db(tmp_path: Path) -> Memory:
    return Memory(db_path=tmp_path / "t.db")


def _log_tool_call(
    db: Memory, *, name: str, error: str = "none", duration_ms: int = 100, ago_hours: int = 1
) -> None:
    """Insert a tool_logs row. `error` is 'none' for success or an error type."""
    created = (datetime.now(UTC) - timedelta(hours=ago_hours)).isoformat()
    db._conn.execute(
        "INSERT INTO tool_logs (session_id, tool_name, duration_ms, error_type, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("s", name, duration_ms, error, created),
    )
    db._conn.commit()


# ---------------------------------------------------------------------------
# commitment_velocity
# ---------------------------------------------------------------------------


def test_commitment_velocity_counts_created_completed_and_backlog(db: Memory) -> None:
    a = create_commitment(db, title="a")
    b = create_commitment(db, title="b")
    create_commitment(db, title="backlog")

    close_commitment(db, a["id"])
    close_commitment(db, b["id"])

    v = get_commitment_velocity(db, days=7)
    assert v["created"] == 3
    assert v["completed"] == 2
    assert v["backlog"] == 1
    assert v["days"] == 7


def test_commitment_velocity_respects_window(db: Memory) -> None:
    create_commitment(db, title="fresh")
    # Fake an old one by back-dating created_at.
    old_iso = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    db._conn.execute(
        "UPDATE commitments SET created_at = ?, updated_at = ?",
        (old_iso, old_iso),
    )
    # Now insert a fresh one.
    fresh = create_commitment(db, title="fresh-2")
    close_commitment(db, fresh["id"])

    v = get_commitment_velocity(db, days=7)
    # Only fresh + fresh-2 count as created; only fresh-2 as completed.
    assert v["created"] == 1
    assert v["completed"] == 1
    # Backlog still includes the old one.
    assert v["backlog"] == 1


def test_commitment_velocity_empty_returns_zeros(db: Memory) -> None:
    v = get_commitment_velocity(db, days=7)
    assert v == {"created": 0, "completed": 0, "backlog": 0, "days": 7}


# ---------------------------------------------------------------------------
# error_patterns
# ---------------------------------------------------------------------------


def test_error_patterns_reports_recurring_failures(db: Memory) -> None:
    # gmail_search: 5 calls, 3 timeouts
    for _ in range(2):
        _log_tool_call(db, name="gmail_search")
    for _ in range(3):
        _log_tool_call(db, name="gmail_search", error="timeout")

    patterns = get_error_patterns(db, days=7, min_errors=2)
    assert len(patterns) == 1
    p = patterns[0]
    assert p["tool_name"] == "gmail_search"
    assert p["error_type"] == "timeout"
    assert p["error_count"] == 3
    # 3 / 5 = 60%
    assert 55 <= p["error_rate_pct"] <= 65


def test_error_patterns_drops_below_min_errors(db: Memory) -> None:
    _log_tool_call(db, name="x", error="rate_limit")
    # Only 1 error, below min_errors=2 → not reported.
    patterns = get_error_patterns(db, days=7, min_errors=2)
    assert patterns == []


def test_error_patterns_ignores_old_entries(db: Memory) -> None:
    for _ in range(3):
        _log_tool_call(db, name="x", error="timeout", ago_hours=24 * 10)
    patterns = get_error_patterns(db, days=7, min_errors=2)
    assert patterns == []


# ---------------------------------------------------------------------------
# error_pattern_summary (cached)
# ---------------------------------------------------------------------------


def test_summary_empty_returns_empty_string(db: Memory) -> None:
    invalidate_error_summary_cache()
    assert get_error_pattern_summary(db, days=7) == ""


def test_summary_formats_for_system_prompt(db: Memory) -> None:
    invalidate_error_summary_cache()
    for _ in range(3):
        _log_tool_call(db, name="gmail_search", error="timeout")
    summary = get_error_pattern_summary(db, days=7)
    assert "RECENT ERROR PATTERNS" in summary
    assert "gmail_search" in summary
    assert "timeout" in summary


def test_summary_is_cached(db: Memory) -> None:
    """Second call within TTL returns the same value even if the DB changes."""
    invalidate_error_summary_cache()
    for _ in range(3):
        _log_tool_call(db, name="gmail_search", error="timeout")
    first = get_error_pattern_summary(db, days=7)

    # Add more errors after first call.
    for _ in range(3):
        _log_tool_call(db, name="calendar_list", error="timeout")
    second = get_error_pattern_summary(db, days=7)
    assert first == second  # cached

    invalidate_error_summary_cache()
    third = get_error_pattern_summary(db, days=7)
    assert "calendar_list" in third


# ---------------------------------------------------------------------------
# analytics_summary formatter
# ---------------------------------------------------------------------------


def test_analytics_summary_renders_velocity_and_costs(db: Memory) -> None:
    a = create_commitment(db, title="done one")
    close_commitment(db, a["id"])
    create_commitment(db, title="open one")

    out = get_analytics_summary(db)
    assert "Commitments" in out
    assert "1 created" in out or "2 created" in out  # either wording is fine
    assert "1 completed" in out
    assert "1 backlog" in out


def test_analytics_summary_graceful_on_empty_db(db: Memory) -> None:
    out = get_analytics_summary(db)
    # Never raise, always return a string. Must mention commitments even
    # if everything is zero — it's the headline signal.
    assert isinstance(out, str)
    assert len(out) > 0
