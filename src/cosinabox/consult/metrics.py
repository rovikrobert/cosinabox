"""In-memory daily metrics for the consult MCP endpoint.

Mirrors cos-agent's per-day rolling counter: calls / cost / average latency
plus the ISO timestamp of the most recent call. Resets automatically when
the local-date-today (per the configured timezone) rolls over.

Intentionally NOT persisted: restart wipes the counters. A DB-backed audit
log is explicitly out of scope for v1 (see the scope doc) and tracked as
a v2 follow-up. For v1, the describe CLI snapshots this dataclass and
prints the current day's totals.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


@dataclass
class Metrics:
    """Daily rolling counters for consult calls.

    Fields:
      * `calls_today`   — number of successful record() invocations today.
      * `cost_today_usd` — accumulated estimated cost in USD.
      * `total_latency_ms` — sum of per-call latencies; `snapshot()` divides
        by `calls_today` for the average.
      * `last_call`     — tz-aware ISO string of the last record() call, or
        None if no calls yet.
      * `timezone`      — IANA tz name used for day-rollover AND last_call
        formatting. Defaults to UTC; callers typically pass the persona's
        configured timezone (see cosinabox.defaults.DEFAULT_TIMEZONE).
      * `_date_str`     — internal: ISO date of the current window. Used to
        detect day rollovers in record() and snapshot().
    """

    calls_today: int = 0
    cost_today_usd: float = 0.0
    total_latency_ms: int = 0
    last_call: str | None = None
    timezone: str = "UTC"
    _date_str: str = field(default="", repr=False)
    # Non-init lock: guards all mutating reads + writes to the counters so
    # concurrent MCP handler invocations (or describe CLI snapshots) cannot
    # interleave increments. Marked repr=False + compare=False so dataclass
    # identity behavior is unaffected.
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def _today_in_tz(self) -> str:
        """Return the ISO date for 'today' in `self.timezone`.

        Drives the day-rollover check in record() and snapshot(). Using the
        configured timezone here — rather than `date.today()` — ensures a
        UTC-hosted server with a PT persona rolls over at 00:00 PT, not 00:00
        UTC. Matches the docstring contract.
        """
        return datetime.now(ZoneInfo(self.timezone)).date().isoformat()

    def record(self, cost_usd: float, latency_ms: float) -> None:
        """Record a single consult call's cost + latency.

        Resets counters if the local date (per `self.timezone`) has rolled
        over since the last record(). `latency_ms` is stored as an integer
        (microsecond resolution is not meaningful for human-facing metrics).
        """
        with self._lock:
            today = self._today_in_tz()
            if self._date_str != today:
                self.calls_today = 0
                self.cost_today_usd = 0.0
                self.total_latency_ms = 0
                self._date_str = today
            self.calls_today += 1
            self.cost_today_usd += cost_usd
            self.total_latency_ms += int(round(latency_ms))
            self.last_call = datetime.now(ZoneInfo(self.timezone)).isoformat()

    def snapshot(self) -> dict[str, Any]:
        """Return today's metrics as a serializable dict.

        If the wall-clock day has rolled over since the last record(), the
        snapshot reflects the rollover (zeros, null last_call) — this matches
        cos-agent and avoids stale values leaking across midnight.
        """
        with self._lock:
            today = self._today_in_tz()
            if self._date_str != today:
                return {
                    "calls_today": 0,
                    "cost_today_usd": 0.0,
                    "avg_latency_ms": 0,
                    "last_call": None,
                }
            avg_ms = int(round(self.total_latency_ms / self.calls_today)) if self.calls_today else 0
            return {
                "calls_today": self.calls_today,
                "cost_today_usd": round(self.cost_today_usd, 4),
                "avg_latency_ms": avg_ms,
                "last_call": self.last_call,
            }


_default: Metrics | None = None


def get_default_metrics() -> Metrics:
    """Return (and lazily construct) the process-wide metrics singleton.

    Uses `cosinabox.defaults.DEFAULT_TIMEZONE`. Callers that need a
    per-persona timezone (e.g., the handler in M3) can mutate the singleton's
    `.timezone` attribute after building it, or instantiate their own
    `Metrics(timezone=...)` and skip the singleton entirely.
    """
    global _default
    if _default is None:
        from cosinabox import defaults

        _default = Metrics(timezone=defaults.DEFAULT_TIMEZONE)
    return _default


def reset_default_metrics() -> None:
    """Test hook — drops the singleton so the next `get_default_metrics()`
    call rebuilds a fresh instance."""
    global _default
    _default = None
