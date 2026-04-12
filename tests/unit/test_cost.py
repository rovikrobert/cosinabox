from __future__ import annotations

from datetime import date

import pytest

from cosinabox.agent.cost import CostExceeded, CostTracker


def test_per_message_cap_blocks_oversized_call() -> None:
    tracker = CostTracker(per_message_cap_usd=0.50, daily_cap_usd=10.00)
    with pytest.raises(CostExceeded, match="per-message"):
        tracker.check_message_cost(0.75)


def test_daily_cap_accumulates_across_messages() -> None:
    tracker = CostTracker(per_message_cap_usd=1.00, daily_cap_usd=2.00)
    tracker.record(0.80, on_date=date(2026, 4, 12))
    tracker.record(0.80, on_date=date(2026, 4, 12))
    with pytest.raises(CostExceeded, match="daily"):
        tracker.record(0.80, on_date=date(2026, 4, 12))


def test_daily_cap_resets_next_day() -> None:
    tracker = CostTracker(per_message_cap_usd=1.00, daily_cap_usd=1.00)
    tracker.record(0.99, on_date=date(2026, 4, 11))
    tracker.record(0.99, on_date=date(2026, 4, 12))  # different day, fine
    assert tracker.spend_on(date(2026, 4, 12)) == pytest.approx(0.99)
