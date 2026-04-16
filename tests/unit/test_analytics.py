from __future__ import annotations

import pytest

from cosinabox.agent.analytics import (
    get_cost_summary,
    get_error_summary,
    get_job_health,
    get_tool_stats,
)
from cosinabox.memory import Memory


@pytest.fixture
def mem(tmp_path):
    return Memory(db_path=tmp_path / "test.db")


class TestAnalytics:
    def test_cost_summary_empty(self, mem):
        result = get_cost_summary(mem)
        assert result["today"] == 0.0
        assert result["week_avg"] == 0.0

    def test_cost_summary_with_data(self, mem):
        from datetime import UTC, datetime
        today = datetime.now(UTC).date().isoformat()
        mem._conn.execute(
            "INSERT INTO daily_costs (date, total_cost, opus_calls, sonnet_calls, tool_calls) "
            "VALUES (?, ?, ?, ?, ?)", (today, 3.50, 2, 10, 15),
        )
        mem._conn.commit()
        result = get_cost_summary(mem)
        assert abs(result["today"] - 3.50) < 0.01

    def test_tool_stats_empty(self, mem):
        result = get_tool_stats(mem)
        assert result["tools"] == []

    def test_tool_stats_with_data(self, mem):
        from datetime import UTC, datetime
        ts = datetime.now(UTC).isoformat()
        for _ in range(5):
            mem._conn.execute(
                "INSERT INTO tool_logs "
                "(session_id, tool_name, duration_ms, error_type, created_at) "
                "VALUES (?, ?, ?, ?, ?)", ("s1", "gmail_search", 100, "none", ts),
            )
        mem._conn.execute(
            "INSERT INTO tool_logs (session_id, tool_name, duration_ms, error_type, created_at) "
            "VALUES (?, ?, ?, ?, ?)", ("s1", "gmail_search", 200, "rate_limit", ts),
        )
        mem._conn.commit()
        result = get_tool_stats(mem)
        assert len(result["tools"]) >= 1
        gmail = result["tools"][0]
        assert gmail["name"] == "gmail_search"
        assert gmail["calls"] == 6
        assert gmail["error_rate"] > 0

    def test_job_health_empty(self, mem):
        result = get_job_health(mem)
        assert result["runs_today"] == 0

    def test_error_summary_empty(self, mem):
        result = get_error_summary(mem)
        assert result["errors"] == []
