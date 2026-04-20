"""Analytics — pure query functions over structured logging tables.

cosinabox-original: cost summary, tool stats, job health, simple error summary.

Ported from cos-agent 2026-04-20 (follow-up to the commitments port):
- ``get_commitment_velocity`` — created/completed/backlog (commitments table).
- ``get_error_patterns`` — recurring failures by tool × error type.
- ``get_error_pattern_summary`` — cached formatter for system-prompt injection.
- ``get_analytics_summary`` — short text block for the CLI / DM.

Blocked ports (not in this file; need dependent tables first):
- ``get_autonomy_score`` (needs ``autonomy_log`` table)
- ``get_decision_latency`` (needs ``decision_memos`` table)
"""

from __future__ import annotations

import time as _time
from datetime import UTC, datetime, timedelta
from typing import Any


def get_cost_summary(db: Any, days: int = 7) -> dict[str, Any]:
    today = datetime.now(UTC).date().isoformat()
    cur = db._conn.execute(
        "SELECT total_cost FROM daily_costs WHERE date = ?",
        (today,),
    )
    row = cur.fetchone()
    today_cost = float(row["total_cost"]) if row else 0.0

    cutoff = (datetime.now(UTC).date() - timedelta(days=days)).isoformat()
    cur = db._conn.execute(
        "SELECT AVG(total_cost) as avg_cost, COUNT(*) as day_count "
        "FROM daily_costs WHERE date >= ?",
        (cutoff,),
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
        tools.append(
            {
                "name": row["tool_name"],
                "calls": calls,
                "errors": errors,
                "error_rate": round(errors / calls, 2) if calls > 0 else 0.0,
            }
        )
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
        {"name": row["job_name"], "failures": row["failures"]} for row in cur.fetchall()
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


# ---------------------------------------------------------------------------
# Commitment velocity (ported 2026-04-20)
# ---------------------------------------------------------------------------


def get_commitment_velocity(db: Any, days: int = 7) -> dict[str, Any]:
    """Commitments throughput: created + completed in-window, total backlog.

    Requires the commitments table (present since the commitments port).
    """
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    created = db._conn.execute(
        "SELECT COUNT(*) AS n FROM commitments WHERE created_at >= ?",
        (cutoff,),
    ).fetchone()["n"]

    completed = db._conn.execute(
        "SELECT COUNT(*) AS n FROM commitments WHERE status = 'done' AND updated_at >= ?",
        (cutoff,),
    ).fetchone()["n"]

    backlog = db._conn.execute(
        "SELECT COUNT(*) AS n FROM commitments WHERE status IN ('open', 'in_progress', 'blocked')",
    ).fetchone()["n"]

    return {
        "created": int(created),
        "completed": int(completed),
        "backlog": int(backlog),
        "days": days,
    }


# ---------------------------------------------------------------------------
# Error patterns + cached summary (ported 2026-04-20)
# ---------------------------------------------------------------------------


def get_error_patterns(
    db: Any,
    *,
    days: int = 7,
    min_errors: int = 2,
) -> list[dict[str, Any]]:
    """Recurring failures grouped by (tool_name, error_type).

    Returns only patterns with ``>= min_errors`` occurrences in the window.
    Each row includes the rate (% of that tool's total calls that failed
    with this error type) so the prompt can prioritize by impact.
    """
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    cur = db._conn.execute(
        """
        WITH totals AS (
            SELECT tool_name, COUNT(*) AS total
            FROM tool_logs WHERE created_at >= ?
            GROUP BY tool_name
        ),
        errors AS (
            SELECT tool_name, error_type, COUNT(*) AS error_count
            FROM tool_logs
            WHERE error_type != 'none' AND created_at >= ?
            GROUP BY tool_name, error_type
            HAVING error_count >= ?
        )
        SELECT e.tool_name, e.error_type, e.error_count,
               e.error_count * 100.0 / t.total AS error_rate_pct
        FROM errors e JOIN totals t ON t.tool_name = e.tool_name
        ORDER BY e.error_count DESC
        LIMIT 10
        """,
        (cutoff, cutoff, min_errors),
    )
    return [dict(row) for row in cur.fetchall()]


# Module-level cache so the system prompt doesn't re-query the DB every
# turn. 5-minute TTL is arbitrary but matches cos-agent and feels right
# for a slow-changing signal. ``_AT`` is ``-inf`` so the first read
# always misses regardless of how small ``time.monotonic()`` is (e.g.,
# fresh CI runners where monotonic is only a few seconds).
_ERROR_SUMMARY_CACHE: str = ""
_ERROR_SUMMARY_AT: float = float("-inf")
_ERROR_SUMMARY_TTL_S: float = 300.0


def invalidate_error_summary_cache() -> None:
    """Clear the cached error pattern summary. Used by tests and
    admin-triggered cache busts.
    """
    global _ERROR_SUMMARY_CACHE, _ERROR_SUMMARY_AT
    _ERROR_SUMMARY_CACHE = ""
    # Sentinel so the cache always looks stale on the next read regardless
    # of what ``time.monotonic()`` returns. Using 0.0 would look fresh for
    # ~5 minutes on any process that started less than TTL seconds ago
    # (e.g., CI runners), causing stale-empty-string leaks between tests.
    _ERROR_SUMMARY_AT = float("-inf")


def get_error_pattern_summary(db: Any, days: int = 7) -> str:
    """Formatted recurring-errors block for injection into the system prompt.

    Cached for ``_ERROR_SUMMARY_TTL_S`` seconds since tool-failure signals
    change slowly — re-querying on every agent turn is wasteful.
    """
    global _ERROR_SUMMARY_CACHE, _ERROR_SUMMARY_AT
    now = _time.monotonic()
    if now - _ERROR_SUMMARY_AT < _ERROR_SUMMARY_TTL_S:
        return _ERROR_SUMMARY_CACHE

    patterns = get_error_patterns(db, days=days)
    if not patterns:
        _ERROR_SUMMARY_CACHE = ""
        _ERROR_SUMMARY_AT = now
        return ""

    lines = []
    for p in patterns:
        rate = round(p.get("error_rate_pct") or 0, 0)
        lines.append(
            f"  - {p['tool_name']}: {p['error_count']}x "
            f"{p.get('error_type') or 'unknown'} errors ({rate:.0f}% failure rate)"
        )
    _ERROR_SUMMARY_CACHE = f"RECENT ERROR PATTERNS (last {days} days):\n" + "\n".join(lines)
    _ERROR_SUMMARY_AT = now
    return _ERROR_SUMMARY_CACHE


# ---------------------------------------------------------------------------
# CLI/DM-friendly summary (ported 2026-04-20)
# ---------------------------------------------------------------------------


def get_analytics_summary(db: Any) -> str:
    """Short formatted block suitable for ``cosinabox analytics`` or a DM.

    Always returns a non-empty string. Individual sections degrade to
    sensible defaults rather than raising — the user should be able to
    pull a summary even if one query fails.
    """
    lines = ["ANALYTICS"]

    try:
        velocity = get_commitment_velocity(db, days=7)
        lines.append(
            f"Commitments (7d): {velocity['created']} created, "
            f"{velocity['completed']} completed, "
            f"{velocity['backlog']} backlog"
        )
    except Exception:
        lines.append("Commitments: unavailable")

    try:
        cost = get_cost_summary(db, days=7)
        lines.append(f"Cost (today / 7d avg): ${cost['today']:.2f} / ${cost['week_avg']:.2f}")
    except Exception:
        lines.append("Cost: unavailable")

    try:
        health = get_job_health(db, days=7)
        if health.get("failing_jobs"):
            failing = ", ".join(f"{j['name']} ({j['failures']}x)" for j in health["failing_jobs"])
            lines.append(f"Failing jobs (7d): {failing}")
    except Exception:
        pass

    return "\n".join(lines)
