"""Structured logging — tool calls, costs, job runs.

Privacy: logs store tool name + duration + error type. Never stores
input parameters or output content.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


def classify_error(exc: Exception) -> str:
    """Classify exception into a loggable bucket."""
    # 1. Check exception class name (httpx.ConnectTimeout, etc.)
    exc_type = type(exc).__name__.lower()
    if "timeout" in exc_type:
        return "timeout"
    if "ratelimit" in exc_type:
        return "rate_limit"

    # 2. Check status_code attribute (httpx, anthropic, googleapiclient)
    status = getattr(exc, "status_code", None)
    if status is None:
        resp = getattr(exc, "resp", None)
        if resp:
            status = getattr(resp, "status", None)
    if status == 429:
        return "rate_limit"
    if status in (401, 403):
        return "auth"
    if isinstance(status, int) and status >= 500:
        return "api_error"

    # 3. Fall back to string matching
    msg = str(exc).lower()
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "429" in msg or "rate" in msg:
        return "rate_limit"
    if "401" in msg or "403" in msg or "auth" in msg:
        return "auth"
    if "invalid" in msg or "missing" in msg or "required" in msg:
        return "validation"
    return "api_error"


class ToolLogger:
    """Write tool execution logs to SQLite."""

    def __init__(self, db: Any) -> None:
        self._conn = db._conn

    def log(
        self,
        *,
        session_id: str,
        tool_name: str,
        duration_ms: int,
        error: Exception | None,
    ) -> None:
        error_type = classify_error(error) if error else "none"
        ts = datetime.now(UTC).isoformat()
        self._conn.execute(
            "INSERT INTO tool_logs (session_id, tool_name, duration_ms, error_type, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, tool_name, duration_ms, error_type, ts),
        )
        self._conn.commit()
