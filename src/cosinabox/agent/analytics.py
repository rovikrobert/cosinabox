"""Analytics — pure query functions over structured logging tables."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


def get_cost_summary(db: Any, days: int = 7) -> dict[str, Any]:
    today = datetime.now(UTC).date().isoformat()
    cur = db._conn.execute(
        "SELECT total_cost FROM daily_costs WHERE date = ?", (today,),
    )
    row = cur.fetchone()
    today_cost = float(row["total_cost"]) if row else 0.0

    cutoff = (datetime.now(UTC).date() - timedelta(days=days)).isoformat()
    cur = db._conn.execute(
        "SELECT AVG(total_cost) as avg_cost, COUNT(*) as day_count "
        "FROM daily_costs WHERE date >= ?", (cutoff,),
    )
    row = cur.fetchone()
    week_avg = float(row["avg_cost"]) if row and row["avg_cost"] else 0.0

    return {"today": today_cost, "week_avg": round(week_avg, 2), "days": days}


def get_tool_stats(db: Any, days: int = 7) -> dict[str, Any]:
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    cur = db._conn.execute(
        "SELECT tool_name, COUNT(*) as calls, "
        "SUM(CASE WHEN error_type != 'none' THEN 1 ELSE 0 END) as errors "
        "FROM tool_logs WHERE created_at >= ? "
        "GROUP BY tool_name ORDER BY calls DESC LIMIT 5",
        (cutoff,),
    )
    tools = []
    for row in cur.fetchall():
        calls = row["calls"]
        errors = row["errors"]
        tools.append({
            "name": row["tool_name"],
            "calls": calls,
            "errors": errors,
            "error_rate": round(errors / calls, 2) if calls > 0 else 0.0,
        })
    return {"tools": tools, "days": days}


def get_job_health(db: Any, days: int = 7) -> dict[str, Any]:
    today = datetime.now(UTC).date().isoformat()
    cur = db._conn.execute(
        "SELECT COUNT(*) as cnt FROM job_runs WHERE created_at >= ?",
        (today + "T00:00:00",),
    )
    runs_today = cur.fetchone()["cnt"]

    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    cur = db._conn.execute(
        "SELECT job_name, COUNT(*) as failures FROM job_runs "
        "WHERE status = 'error' AND created_at >= ? "
        "GROUP BY job_name ORDER BY failures DESC LIMIT 5",
        (cutoff,),
    )
    failing_jobs = [
        {"name": row["job_name"], "failures": row["failures"]}
        for row in cur.fetchall()
    ]

    return {"runs_today": runs_today, "failing_jobs": failing_jobs, "days": days}


def get_error_summary(db: Any, hours: int = 24) -> dict[str, Any]:
    cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    cur = db._conn.execute(
        "SELECT error_type, COUNT(*) as cnt FROM tool_logs "
        "WHERE error_type != 'none' AND created_at >= ? "
        "GROUP BY error_type ORDER BY cnt DESC LIMIT 3",
        (cutoff,),
    )
    errors = [{"type": row["error_type"], "count": row["cnt"]} for row in cur.fetchall()]
    return {"errors": errors, "hours": hours}
