"""Tests for the auth_health_status persistence layer.

Uses a real on-disk SQLite file (sqlite3 is stdlib, fast). No mocking
the DB — the layer's whole purpose is talking to it correctly.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from cosinabox.jobs.auth_health_persist import (
    AUTH_HEALTH_SCHEMA,
    read_auth_health,
    record_auth_health,
)


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(AUTH_HEALTH_SCHEMA)
    return conn


def test_record_then_read_returns_row(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    record_auth_health(db, account_index=1, email="rovik@example.com", ok=True)
    rows = read_auth_health(db)
    assert len(rows) == 1
    assert rows[0]["account_index"] == 1
    assert rows[0]["email"] == "rovik@example.com"
    assert rows[0]["last_status"] == "ok"
    assert rows[0]["last_check_at"]  # ISO timestamp string


def test_record_upserts_on_account_index(tmp_path: Path) -> None:
    """Writing twice for the same account_index updates, not inserts."""
    db = tmp_path / "memory.db"
    record_auth_health(db, account_index=1, email="rovik@example.com", ok=True)
    record_auth_health(db, account_index=1, email="rovik@example.com", ok=False)
    rows = read_auth_health(db)
    assert len(rows) == 1
    assert rows[0]["last_status"] == "failed"


def test_record_multiple_accounts(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    record_auth_health(db, account_index=1, email="a@example.com", ok=True)
    record_auth_health(db, account_index=2, email="b@example.com", ok=False)
    rows = read_auth_health(db)
    assert len(rows) == 2
    by_idx = {r["account_index"]: r for r in rows}
    assert by_idx[1]["last_status"] == "ok"
    assert by_idx[2]["last_status"] == "failed"


def test_read_returns_empty_list_when_table_empty(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    _connect(db).close()
    assert read_auth_health(db) == []


def test_read_returns_empty_list_when_db_missing(tmp_path: Path) -> None:
    """A fresh user-repo with no memory.db yet should return [], not crash."""
    db = tmp_path / "does-not-exist.db"
    assert read_auth_health(db) == []


def test_schema_is_idempotent(tmp_path: Path) -> None:
    """Creating the schema twice (e.g., on app restart) must not error."""
    db = tmp_path / "memory.db"
    _connect(db).close()
    _connect(db).close()


def test_rows_ordered_by_account_index(tmp_path: Path) -> None:
    """read_auth_health sorts by account_index so /status renders 1, 2, 3 in order."""
    db = tmp_path / "memory.db"
    record_auth_health(db, account_index=3, email="c@example.com", ok=True)
    record_auth_health(db, account_index=1, email="a@example.com", ok=True)
    record_auth_health(db, account_index=2, email="b@example.com", ok=False)
    rows = read_auth_health(db)
    assert [r["account_index"] for r in rows] == [1, 2, 3]
