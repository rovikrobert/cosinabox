"""Per-message and daily cost caps for the agent loop.

Defaults come from spec Layer 1:
- Per-message cap: $0.75 (cost runaways are real)
- Daily cap: $15 (forcing function for greedy prompts)

The constants live in defaults.py once that module exists (Task T2.1).
Until then, callers pass caps explicitly.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime


class CostExceeded(Exception):
    """Raised when a cost cap would be exceeded by the next call."""


class CostTracker:
    def __init__(
        self,
        *,
        per_message_cap_usd: float,
        daily_cap_usd: float,
    ) -> None:
        self.per_message_cap_usd = per_message_cap_usd
        self.daily_cap_usd = daily_cap_usd
        self._daily_spend: dict[date, float] = defaultdict(float)

    def check_message_cost(self, estimated_usd: float) -> None:
        if estimated_usd > self.per_message_cap_usd:
            raise CostExceeded(
                f"per-message cost ${estimated_usd:.4f} exceeds cap "
                f"${self.per_message_cap_usd:.4f}"
            )

    def record(self, actual_usd: float, *, on_date: date | None = None) -> None:
        d = on_date or datetime.now(UTC).date()
        if self._daily_spend[d] + actual_usd > self.daily_cap_usd:
            raise CostExceeded(
                f"daily spend ${self._daily_spend[d] + actual_usd:.4f} "
                f"exceeds cap ${self.daily_cap_usd:.4f}"
            )
        self._daily_spend[d] += actual_usd

    def spend_on(self, d: date) -> float:
        return self._daily_spend[d]
