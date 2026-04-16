"""Per-message and daily cost caps for the agent loop.

Defaults come from spec Layer 1:
- Per-message cap: $0.75 (cost runaways are real)
- Daily cap: $15 (forcing function for greedy prompts)

The constants live in defaults.py once that module exists (Task T2.1).
Until then, callers pass caps explicitly.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from datetime import UTC, date, datetime
from typing import Any

PRICING = {
    "claude-opus-4-6": {
        "input": 15.0,
        "output": 75.0,
        "cache_write": 18.75,
        "cache_read": 1.50,
    },
    "claude-sonnet-4-6": {
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.80,
        "output": 4.0,
        "cache_write": 1.00,
        "cache_read": 0.08,
    },
}


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Estimate cost in USD for a single API call."""
    prices = PRICING.get(model, PRICING["claude-sonnet-4-6"])
    input_cost = (input_tokens / 1_000_000) * prices["input"]
    output_cost = (output_tokens / 1_000_000) * prices["output"]
    cache_write_cost = (cache_creation_tokens / 1_000_000) * prices["cache_write"]
    cache_read_cost = (cache_read_tokens / 1_000_000) * prices["cache_read"]
    return input_cost + output_cost + cache_write_cost + cache_read_cost


def estimate_cost_with_advisor(
    executor_model: str,
    iterations: list[dict[str, Any]],
) -> float:
    """Estimate cost from usage.iterations array (advisor-enabled calls).

    "message" iterations bill at executor rates.
    "advisor_message" iterations bill at the iteration's own model rates.
    """
    total = 0.0
    for it in iterations:
        model = it["model"] if it["type"] == "advisor_message" else executor_model
        total += estimate_cost(
            model,
            it.get("input_tokens", 0),
            it.get("output_tokens", 0),
            cache_creation_tokens=it.get("cache_creation_input_tokens", 0) or 0,
            cache_read_tokens=it.get("cache_read_input_tokens", 0) or 0,
        )
    return total


class CostExceeded(Exception):
    """Raised when a cost cap would be exceeded by the next call."""


class CostTracker:
    def __init__(
        self,
        *,
        per_message_cap_usd: float,
        daily_cap_usd: float,
        db: Any | None = None,
    ) -> None:
        self.per_message_cap_usd = per_message_cap_usd
        self.daily_cap_usd = daily_cap_usd
        self._daily_spend: dict[date, float] = defaultdict(float)
        self._db = db
        self._lock = threading.Lock()

        # Load today's spend from DB if available
        if self._db is not None:
            today = datetime.now(UTC).date().isoformat()
            cur = self._db._conn.execute(
                "SELECT total_cost FROM daily_costs WHERE date = ?",
                (today,),
            )
            row = cur.fetchone()
            if row:
                self._daily_spend[datetime.now(UTC).date()] = float(row["total_cost"])

    def check_message_cost(self, estimated_usd: float) -> None:
        if estimated_usd > self.per_message_cap_usd:
            raise CostExceeded(
                f"per-message cost ${estimated_usd:.4f} exceeds cap ${self.per_message_cap_usd:.4f}"
            )

    def record(self, actual_usd: float, *, on_date: date | None = None) -> None:
        d = on_date or datetime.now(UTC).date()
        with self._lock:
            if self._daily_spend[d] + actual_usd > self.daily_cap_usd:
                raise CostExceeded(
                    f"daily spend ${self._daily_spend[d] + actual_usd:.4f} "
                    f"exceeds cap ${self.daily_cap_usd:.4f}"
                )
            self._daily_spend[d] += actual_usd

        # Persist via atomic SQL increment (thread-safe)
        if self._db is not None:
            date_str = d.isoformat()
            self._db._conn.execute(
                "INSERT INTO daily_costs (date, total_cost) VALUES (?, ?) "
                "ON CONFLICT(date) DO UPDATE SET total_cost = total_cost + ?",
                (date_str, actual_usd, actual_usd),
            )
            self._db._conn.commit()

    def spend_on(self, d: date) -> float:
        return self._daily_spend[d]
