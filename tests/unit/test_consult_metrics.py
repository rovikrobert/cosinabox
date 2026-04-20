"""Unit tests for the consult MCP endpoint's in-memory daily metrics.

TDD: written before `cosinabox.consult.metrics` exists. Mirrors cos-agent's
metrics logic (reset-daily, tz-aware `last_call`) but reshaped as a
dataclass + explicit timezone setter so tests can pin behavior without
poking module globals.
"""

from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from cosinabox.consult.metrics import (
    Metrics,
    get_default_metrics,
    reset_default_metrics,
)


def test_metrics_empty_snapshot_has_zero_avg_and_null_last_call() -> None:
    m = Metrics()
    snap = m.snapshot()
    assert snap == {
        "calls_today": 0,
        "cost_today_usd": 0.0,
        "avg_latency_ms": 0,
        "last_call": None,
    }


def _patch_metrics_now(monkeypatch: pytest.MonkeyPatch, current: list[dt.datetime]) -> None:
    """Pin `cosinabox.consult.metrics.datetime.now(tz)` to return current[0].

    Tests mutate `current[0]` in-place to advance the clock. Rollover logic
    now keys off `datetime.now(tz).date()`, so patching datetime is the
    right seam.
    """

    class _FakeDatetime(dt.datetime):
        @classmethod
        def now(cls, tz: dt.tzinfo | None = None) -> dt.datetime:  # type: ignore[override]
            return current[0].astimezone(tz) if tz is not None else current[0]

    monkeypatch.setattr("cosinabox.consult.metrics.datetime", _FakeDatetime)


def test_metrics_record_increments_and_averages(monkeypatch: pytest.MonkeyPatch) -> None:
    current = [dt.datetime(2026, 4, 20, 12, 0, tzinfo=dt.UTC)]
    _patch_metrics_now(monkeypatch, current)

    m = Metrics(timezone="UTC")
    m.record(cost_usd=0.01, latency_ms=100)
    m.record(cost_usd=0.02, latency_ms=300)
    snap = m.snapshot()
    assert snap["calls_today"] == 2
    # Cost is rounded to 4 decimals.
    assert snap["cost_today_usd"] == pytest.approx(0.03, abs=1e-9)
    # (100 + 300) / 2 = 200.
    assert snap["avg_latency_ms"] == 200
    # last_call is an ISO string, not None.
    assert isinstance(snap["last_call"], str)
    assert snap["last_call"].startswith("2026-04-20")


def test_metrics_snapshot_rounds_cost_to_4dp(monkeypatch: pytest.MonkeyPatch) -> None:
    current = [dt.datetime(2026, 4, 20, 12, 0, tzinfo=dt.UTC)]
    _patch_metrics_now(monkeypatch, current)

    m = Metrics()
    m.record(cost_usd=0.00012345, latency_ms=10)
    snap = m.snapshot()
    # 0.00012345 rounded to 4 decimals is 0.0001.
    assert snap["cost_today_usd"] == pytest.approx(0.0001, abs=1e-9)


def test_metrics_reset_on_day_rollover(monkeypatch: pytest.MonkeyPatch) -> None:
    current = [dt.datetime(2026, 4, 20, 12, 0, tzinfo=dt.UTC)]
    _patch_metrics_now(monkeypatch, current)

    m = Metrics()
    m.record(cost_usd=0.10, latency_ms=500)
    m.record(cost_usd=0.20, latency_ms=700)
    assert m.snapshot()["calls_today"] == 2

    # Advance wall-clock day.
    current[0] = dt.datetime(2026, 4, 21, 12, 0, tzinfo=dt.UTC)

    # Pre-record snapshot should reflect the rollover (stale day → zeros).
    stale = m.snapshot()
    assert stale["calls_today"] == 0
    assert stale["cost_today_usd"] == 0.0
    assert stale["avg_latency_ms"] == 0
    assert stale["last_call"] is None

    # Recording on the new day starts a fresh tally.
    m.record(cost_usd=0.05, latency_ms=250)
    snap = m.snapshot()
    assert snap["calls_today"] == 1
    assert snap["cost_today_usd"] == pytest.approx(0.05, abs=1e-9)
    assert snap["avg_latency_ms"] == 250


def test_metrics_no_division_by_zero_when_empty() -> None:
    # Regression: avg_latency_ms must not KeyError or ZeroDivisionError when
    # no calls have been recorded (matches cos-agent guard).
    m = Metrics()
    snap = m.snapshot()
    assert snap["avg_latency_ms"] == 0


def test_metrics_last_call_respects_configured_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Mid-day UTC on 2026-04-20 is 05:00 PT the same day — no rollover ambiguity.
    current = [dt.datetime(2026, 4, 20, 12, 0, tzinfo=dt.UTC)]
    _patch_metrics_now(monkeypatch, current)

    m = Metrics(timezone="America/Los_Angeles")
    m.record(cost_usd=0.01, latency_ms=100)
    snap = m.snapshot()
    # LA offset is -07:00 or -08:00 depending on DST. Either way, the ISO
    # string must carry a timezone suffix — i.e., be tz-aware (the plan
    # explicitly requires this).
    last_call = snap["last_call"]
    assert isinstance(last_call, str)
    assert ("-07:00" in last_call) or ("-08:00" in last_call)


def test_metrics_day_rollover_uses_configured_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Day rollover must honor self.timezone, not system-local date.today().

    Regression: a UTC-hosted server with timezone='America/Los_Angeles'
    would previously roll over at 00:00 UTC (17:00 PT) instead of 00:00 PT,
    contradicting the docstring.
    """
    la = dt.timezone(dt.timedelta(hours=-7))  # PT in DST — matches 2026-04-20.
    current = [dt.datetime(2026, 4, 20, 23, 30, tzinfo=la)]

    class _FakeDatetime(dt.datetime):
        @classmethod
        def now(cls, tz: dt.tzinfo | None = None) -> dt.datetime:  # type: ignore[override]
            return current[0].astimezone(tz) if tz is not None else current[0]

    monkeypatch.setattr("cosinabox.consult.metrics.datetime", _FakeDatetime)

    m = Metrics(timezone="America/Los_Angeles")

    # 2026-04-20 23:30 PT — still day 20.
    m.record(cost_usd=0.1, latency_ms=100)
    # Advance to 23:45 PT — still day 20.
    current[0] = dt.datetime(2026, 4, 20, 23, 45, tzinfo=la)
    m.record(cost_usd=0.2, latency_ms=200)
    # Two calls on the same PT day: no rollover should have occurred.
    assert m.snapshot()["calls_today"] == 2

    # Advance to 2026-04-21 00:05 PT — new PT day, should reset.
    current[0] = dt.datetime(2026, 4, 21, 0, 5, tzinfo=la)
    m.record(cost_usd=0.05, latency_ms=50)
    assert m.snapshot()["calls_today"] == 1


def test_default_metrics_singleton_returns_same_instance() -> None:
    reset_default_metrics()
    first = get_default_metrics()
    second = get_default_metrics()
    assert first is second


def test_default_metrics_reset_hook_drops_instance() -> None:
    reset_default_metrics()
    first = get_default_metrics()
    reset_default_metrics()
    second = get_default_metrics()
    assert first is not second


def test_metrics_record_is_thread_safe() -> None:
    """50 concurrent record() calls must aggregate without losing updates.

    Counters are read-modify-write across four fields; a missing lock can
    drop increments. Test may still pass on CPython via GIL luck — the
    lock is required to pin the contract.
    """
    m = Metrics()

    def _one() -> None:
        m.record(cost_usd=0.01, latency_ms=10)

    with ThreadPoolExecutor(max_workers=50) as ex:
        list(ex.map(lambda _: _one(), range(50)))

    snap = m.snapshot()
    assert snap["calls_today"] == 50
    assert snap["cost_today_usd"] == pytest.approx(0.5, abs=1e-9)
    assert snap["avg_latency_ms"] == 10


def test_metrics_snapshot_shape_is_exactly_four_keys() -> None:
    # Guard the public snapshot contract — callers (describe CLI, M5) depend
    # on this exact key set. Extra keys are breaking changes.
    m = Metrics()
    snap: dict[str, Any] = m.snapshot()
    assert set(snap.keys()) == {
        "calls_today",
        "cost_today_usd",
        "avg_latency_ms",
        "last_call",
    }
