"""SQLite memory backend.

Schema:
    CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp TEXT NOT NULL  -- ISO-8601 UTC
    );
    CREATE INDEX idx_messages_session_ts ON messages (session_id, timestamp);
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session_ts
    ON messages (session_id, timestamp);

CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    messages_summarized INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_summaries_session
    ON summaries (session_id);

CREATE TABLE IF NOT EXISTS tool_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    error_type TEXT NOT NULL DEFAULT 'none',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_logs_created ON tool_logs (created_at);
CREATE INDEX IF NOT EXISTS idx_tool_logs_tool ON tool_logs (tool_name);

CREATE TABLE IF NOT EXISTS daily_costs (
    date TEXT PRIMARY KEY,
    total_cost REAL NOT NULL DEFAULT 0,
    opus_calls INTEGER NOT NULL DEFAULT 0,
    sonnet_calls INTEGER NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    status TEXT NOT NULL,
    output_length INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_runs_created ON job_runs (created_at);

CREATE TABLE IF NOT EXISTS gmail_poll_state (
    account_index INTEGER PRIMARY KEY,
    last_check_ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processed_message_ids (
    message_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS extraction_state (
    key TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS debrief_state (
    ical_uid TEXT PRIMARY KEY,
    debriefed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scheduling_requests (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL,
    requested_by TEXT NOT NULL DEFAULT 'owner',
    date_range_start TEXT NOT NULL,
    date_range_end TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposing'
        CHECK(status IN (
            'proposing', 'rovik_review', 'polling', 'backchannel',
            'converged', 'booked', 'cancelled', 'expired'
        )),
    preferred_timezone TEXT DEFAULT 'UTC',
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scheduling_requests_status ON scheduling_requests(status);

CREATE TABLE IF NOT EXISTS scheduling_participants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL REFERENCES scheduling_requests(id),
    name TEXT NOT NULL,
    email TEXT,
    telegram_id TEXT,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    channel TEXT NOT NULL DEFAULT 'gmail'
        CHECK(channel IN ('telegram', 'gmail')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'sent', 'responded', 'nudged', 'no_response')),
    gmail_thread_id TEXT,
    gmail_draft_id TEXT,
    outreach_sent_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scheduling_participants_request ON scheduling_participants(request_id);

CREATE TABLE IF NOT EXISTS scheduling_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL REFERENCES scheduling_requests(id),
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    score REAL DEFAULT 0.0,
    requires_move TEXT,
    move_approved INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scheduling_slots_request ON scheduling_slots(request_id);

CREATE TABLE IF NOT EXISTS scheduling_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL REFERENCES scheduling_requests(id),
    participant_id INTEGER NOT NULL REFERENCES scheduling_participants(id),
    slot_id INTEGER NOT NULL REFERENCES scheduling_slots(id),
    response TEXT NOT NULL CHECK(response IN ('yes', 'if_needed', 'no')),
    responded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scheduling_responses_request ON scheduling_responses(request_id);

CREATE TABLE IF NOT EXISTS scheduling_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL REFERENCES scheduling_requests(id),
    event_id TEXT NOT NULL,
    original_start TEXT NOT NULL,
    original_end TEXT NOT NULL,
    new_start TEXT NOT NULL,
    new_end TEXT NOT NULL,
    undone INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scheduling_moves_request ON scheduling_moves(request_id);
"""


class Memory:
    """SQLite-backed conversation memory.

    Each row is a single message. Session isolation is by `session_id`.
    Scheduled jobs use a fresh session_id per run (see Layer 1 default
    "Scheduled jobs use isolated session contexts").
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,  # APScheduler + Telegram use different threads
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def store_message(
        self,
        *,
        role: str,
        content: str,
        session_id: str,
        timestamp: datetime | None = None,
    ) -> None:
        ts = (timestamp or datetime.now(UTC)).isoformat()
        self._conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?,?,?,?)",
            (session_id, role, content, ts),
        )
        self._conn.commit()

    def recent_messages(self, *, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT role, content, timestamp FROM messages "
            "WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]

    def message_count(self, *, session_id: str) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?",
            (session_id,),
        )
        return cur.fetchone()[0]

    def oldest_messages(
        self, *, session_id: str, count: int,
    ) -> list[dict[str, Any]]:
        """Return the oldest N messages for a session (for summarization)."""
        cur = self._conn.execute(
            "SELECT id, role, content FROM messages "
            "WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, count),
        )
        return [dict(row) for row in cur.fetchall()]

    def delete_messages_by_ids(self, ids: list[int]) -> int:
        if not ids:
            return 0
        placeholders = ",".join("?" * len(ids))
        cur = self._conn.execute(
            f"DELETE FROM messages WHERE id IN ({placeholders})", ids,
        )
        self._conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------
    # Summaries
    # ------------------------------------------------------------------

    def store_summary(
        self,
        *,
        session_id: str,
        summary: str,
        messages_summarized: int,
    ) -> None:
        # Keep only the latest summary per session
        self._conn.execute(
            "DELETE FROM summaries WHERE session_id = ?", (session_id,),
        )
        ts = datetime.now(UTC).isoformat()
        self._conn.execute(
            "INSERT INTO summaries (session_id, summary, messages_summarized, created_at) "
            "VALUES (?,?,?,?)",
            (session_id, summary, messages_summarized, ts),
        )
        self._conn.commit()

    def get_latest_summary(self, *, session_id: str) -> str | None:
        cur = self._conn.execute(
            "SELECT summary FROM summaries WHERE session_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (session_id,),
        )
        row = cur.fetchone()
        return row["summary"] if row else None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def clear_old(self, *, older_than_days: int) -> int:
        cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat()
        cur = self._conn.execute("DELETE FROM messages WHERE timestamp < ?", (cutoff,))
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()
