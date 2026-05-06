"""Persistence for `auth_health` per-account state.

The auth_health watcher (jobs/auth_health.py) maintains an in-memory
dict of per-account refresh-token health. That state is per-process
and disappears on restart. This module persists it to the user repo's
``memory.db`` so:

  - `/status` can read the latest health without waiting for the next
    auth_health tick.
  - A bot restart doesn't lose the prior known state.

Schema is intentionally minimal: one row per account index, last-known
status only. No history; the auth_health alerts already capture
transitions.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

AUTH_HEALTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS auth_health_status (
    account_index INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    last_status TEXT NOT NULL,
    last_check_at TEXT NOT NULL
);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection and ensure the schema exists. Idempotent."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(AUTH_HEALTH_SCHEMA)
    conn.commit()
    return conn


def record_auth_health(db_path: Path, *, account_index: int, email: str, ok: bool) -> None:
    """Insert or update the per-account auth-health row.

    Status is the literal string ``'ok'`` or ``'failed'``. Callers should
    skip writing on transient errors so the prior row is preserved
    (mirrors the in-memory ``_health`` dict semantic in ``auth_health.py``).
    """
    status = "ok" if ok else "failed"
    now = datetime.now(UTC).isoformat()
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO auth_health_status (account_index, email, last_status, last_check_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(account_index) DO UPDATE SET
                email = excluded.email,
                last_status = excluded.last_status,
                last_check_at = excluded.last_check_at
            """,
            (account_index, email, status, now),
        )
        conn.commit()
    finally:
        conn.close()


def read_auth_health(db_path: Path) -> list[dict[str, Any]]:
    """Return all per-account health rows ordered by account_index.

    Returns ``[]`` if the DB file doesn't exist yet (fresh user-repo
    before auth_health has ticked) — callers should treat empty as "no
    data, hide the row" rather than rendering "(unknown)".
    """
    if not db_path.exists():
        return []
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "SELECT account_index, email, last_status, last_check_at "
            "FROM auth_health_status ORDER BY account_index"
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
