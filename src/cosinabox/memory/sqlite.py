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
        self._conn = sqlite3.connect(self.db_path)
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

    def recent_messages(
        self, *, session_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT role, content, timestamp FROM messages "
            "WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]

    def clear_old(self, *, older_than_days: int) -> int:
        cutoff = (
            datetime.now(UTC) - timedelta(days=older_than_days)
        ).isoformat()
        cur = self._conn.execute(
            "DELETE FROM messages WHERE timestamp < ?", (cutoff,)
        )
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()
