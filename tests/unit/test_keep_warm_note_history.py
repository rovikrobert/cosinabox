# ruff: noqa: I001
"""Tests for keep_warm_note_history table + CRUD."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from cosinabox.memory import Memory
from cosinabox.memory.keep_warm_history import archive_note


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


def test_archive_note_inserts_row(db: Memory) -> None:
    archive_note(
        db,
        person_record_id="rec_123",
        person_name="Sarah Chen",
        note="Send proposal by Friday",
        reason="user_update",
    )
    with db.lock:
        cur = db._conn.execute("SELECT * FROM keep_warm_note_history")
        rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0]["person_record_id"] == "rec_123"
    assert rows[0]["person_name"] == "Sarah Chen"
    assert rows[0]["note"] == "Send proposal by Friday"
    assert rows[0]["reason"] == "user_update"
    # archived_at is a valid ISO-8601 UTC timestamp
    datetime.fromisoformat(rows[0]["archived_at"])


def test_archive_note_accepts_null_reason(db: Memory) -> None:
    archive_note(
        db,
        person_record_id="rec_1",
        person_name=None,
        note="old note",
        reason=None,
    )
    with db.lock:
        cur = db._conn.execute("SELECT reason, person_name FROM keep_warm_note_history")
        row = cur.fetchone()
    assert row["reason"] is None
    assert row["person_name"] is None


def test_archive_note_multiple_rows_for_same_person(db: Memory) -> None:
    """Same person gets multiple rows over time."""
    for text in ["first", "second", "third"]:
        archive_note(
            db,
            person_record_id="rec_x",
            person_name="X",
            note=text,
            reason=None,
        )
    with db.lock:
        cur = db._conn.execute(
            "SELECT COUNT(*) FROM keep_warm_note_history WHERE person_record_id = ?",
            ("rec_x",),
        )
        assert cur.fetchone()[0] == 3
