"""Unit tests for the consult MCP endpoint's in-memory daily metrics.

TDD: written before `cosinabox.consult.metrics` exists. Mirrors cos-agent's
metrics logic (reset-daily, tz-aware `last_call`) but reshaped as a
dataclass + explicit timezone setter so tests can pin behavior without
poking module globals.
"""

from __future__ import annotations

import datetime as dt
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


def test_metrics_record_increments_and_averages(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_date = dt.date(2026, 4, 20)

    class _FixedDate(dt.date):
        @classmethod
        def today(cls) -> dt.date:  # type: ignore[override]
            return fixed_date

    monkeypatch.setattr("cosinabox.consult.metrics.date", _FixedDate)

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
    fixed_date = dt.date(2026, 4, 20)

    class _FixedDate(dt.date):
        @classmethod
        def today(cls) -> dt.date:  # type: ignore[override]
            return fixed_date

    monkeypatch.setattr("cosinabox.consult.metrics.date", _FixedDate)

    m = Metrics()
    m.record(cost_usd=0.00012345, latency_ms=10)
    snap = m.snapshot()
    # 0.00012345 rounded to 4 decimals is 0.0001.
    assert snap["cost_today_usd"] == pytest.approx(0.0001, abs=1e-9)


def test_metrics_reset_on_day_rollover(monkeypatch: pytest.MonkeyPatch) -> None:
    day: list[dt.date] = [dt.date(2026, 4, 20)]

    class _MovingDate(dt.date):
        @classmethod
        def today(cls) -> dt.date:  # type: ignore[override]
            return day[0]

    monkeypatch.setattr("cosinabox.consult.metrics.date", _MovingDate)

    m = Metrics()
    m.record(cost_usd=0.10, latency_ms=500)
    m.record(cost_usd=0.20, latency_ms=700)
    assert m.snapshot()["calls_today"] == 2

    # Advance wall-clock day.
    day[0] = dt.date(2026, 4, 21)

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
    fixed_date = dt.date(2026, 4, 20)

    class _FixedDate(dt.date):
        @classmethod
        def today(cls) -> dt.date:  # type: ignore[override]
            return fixed_date

    monkeypatch.setattr("cosinabox.consult.metrics.date", _FixedDate)

    m = Metrics(timezone="America/Los_Angeles")
    m.record(cost_usd=0.01, latency_ms=100)
    snap = m.snapshot()
    # LA offset is -07:00 or -08:00 depending on DST. Either way, the ISO
    # string must carry a timezone suffix — i.e., be tz-aware (the plan
    # explicitly requires this).
    last_call = snap["last_call"]
    assert isinstance(last_call, str)
    assert ("-07:00" in last_call) or ("-08:00" in last_call)


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
