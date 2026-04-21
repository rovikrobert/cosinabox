# ruff: noqa: I001
"""Tests for keep_warm_note_history table + CRUD."""

from __future__ import annotations

from pathlib import Path

import pytest

from cosinabox.memory import Memory


@pytest.fixture
def db(tmp_path: Path) -> Memory:
    return Memory(db_path=tmp_path / "test.db")


def test_keep_warm_note_history_table_exists(db: Memory) -> None:
    """Memory init creates the keep_warm_note_history table."""
    with db.lock:
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            ("keep_warm_note_history",),
        )
        assert cur.fetchone() is not None


def test_keep_warm_note_history_schema(db: Memory) -> None:
    """Table has the expected columns."""
    with db.lock:
        cur = db._conn.execute("PRAGMA table_info(keep_warm_note_history)")
        cols = {row["name"]: row["type"] for row in cur.fetchall()}
    assert cols == {
        "id": "INTEGER",
        "person_record_id": "TEXT",
        "person_name": "TEXT",
        "note": "TEXT",
        "archived_at": "TEXT",
        "reason": "TEXT",
    }


def test_keep_warm_note_history_index_exists(db: Memory) -> None:
    """Composite index on (person_record_id, archived_at) exists for history lookups."""
    with db.lock:
        cur = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            ("idx_kwh_person_time",),
        )
        assert cur.fetchone() is not None
