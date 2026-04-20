"""Unit tests for the consult MCP endpoint's in-memory hourly rate limiter.

Red-green-commit TDD: these tests are written first, the module under test
(`cosinabox.consult.rate_limit`) does not exist yet, so importing must fail
before implementation lands. Once the module is in place, the suite pins:

  * counter behavior (allow/deny around the limit),
  * wall-clock window rollover (via monkeypatched `time.time`),
  * `snapshot()` shape,
  * module-level singleton accessor + reset hook,
  * the "fresh instance starts at current wall-clock" invariant the plan
    explicitly calls out (NOT `0.0` or `float('-inf')`).
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from cosinabox.consult.rate_limit import (
    RateLimiter,
    get_default_rate_limiter,
    reset_default_rate_limiter,
)


def test_rate_limiter_allows_up_to_limit_then_denies() -> None:
    limiter = RateLimiter(limit=3)
    assert limiter.allow() is True
    assert limiter.allow() is True
    assert limiter.allow() is True
    # 4th call over the limit — denied.
    assert limiter.allow() is False


def test_rate_limiter_resets_after_window_elapses(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pin time so we control the window rollover exactly.
    now = [1_000_000.0]

    def fake_time() -> float:
        return now[0]

    monkeypatch.setattr(time, "time", fake_time)

    limiter = RateLimiter(limit=2, window_start=fake_time())
    assert limiter.allow() is True
    assert limiter.allow() is True
    assert limiter.allow() is False

    # Advance past the 1-hour window.
    now[0] += 3601
    # First call in the new window succeeds AND resets the counter.
    assert limiter.allow() is True
    # One more still within the new window.
    assert limiter.allow() is True
    assert limiter.allow() is False


def test_rate_limiter_snapshot_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pin wall-clock so window_start doesn't get auto-rolled on first allow().
    monkeypatch.setattr(time, "time", lambda: 500.0)
    limiter = RateLimiter(limit=5, window_start=500.0)
    limiter.allow()
    snap: dict[str, Any] = limiter.snapshot()
    assert snap == {"count": 1, "limit": 5, "window_start": 500.0}


def test_rate_limiter_default_window_seconds_is_one_hour() -> None:
    # Guards the "hourly" part of the design. If someone changes the default
    # window, this test forces them to acknowledge it.
    limiter = RateLimiter(limit=1)
    assert limiter.window_seconds == 3600


def test_default_singleton_accessor_returns_same_instance() -> None:
    reset_default_rate_limiter()
    first = get_default_rate_limiter()
    second = get_default_rate_limiter()
    assert first is second


def test_default_singleton_uses_defaults_module_limit() -> None:
    from cosinabox import defaults

    reset_default_rate_limiter()
    limiter = get_default_rate_limiter()
    assert limiter.limit == defaults.CONSULT_RATE_LIMIT_PER_HOUR


def test_default_singleton_reset_hook_drops_instance() -> None:
    reset_default_rate_limiter()
    first = get_default_rate_limiter()
    reset_default_rate_limiter()
    second = get_default_rate_limiter()
    # After reset, accessor rebuilds a fresh instance.
    assert first is not second


def test_rate_limiter_allow_is_thread_safe() -> None:
    """50 concurrent callers against limit=30 must see exactly 30 True / 20 False.

    Without a lock, two threads can pass the `count < limit` check before
    either increments, leaking extra True responses. The test may pass on
    CPython via GIL luck — the lock is still required to pin the behavior.
    """
    limiter = RateLimiter(limit=30, window_start=time.time())

    with ThreadPoolExecutor(max_workers=50) as ex:
        results = list(ex.map(lambda _: limiter.allow(), range(50)))

    assert results.count(True) == 30
    assert results.count(False) == 20


def test_default_singleton_fresh_instance_window_starts_at_wall_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Plan-level invariant: fresh instance's window_start is current time.time(),
    # NOT 0.0 or float('-inf'). Otherwise the first-ever call would appear to
    # be in a window that started at the Unix epoch — which is fine for the
    # "allow" logic but would make snapshots hard to read.
    monkeypatch.setattr(time, "time", lambda: 5_000_000.0)
    reset_default_rate_limiter()
    limiter = get_default_rate_limiter()
    assert limiter.window_start == 5_000_000.0
