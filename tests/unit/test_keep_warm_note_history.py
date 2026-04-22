# ruff: noqa: I001
"""Tests for keep_warm_note_history table + CRUD."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from cosinabox.memory import Memory
from cosinabox.memory.keep_warm_history import archive_note, list_note_history


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
    )
    with db.lock:
        cur = db._conn.execute("SELECT * FROM keep_warm_note_history")
        rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0]["person_record_id"] == "rec_123"
    assert rows[0]["person_name"] == "Sarah Chen"
    assert rows[0]["note"] == "Send proposal by Friday"
    # archived_at is a valid ISO-8601 UTC timestamp
    datetime.fromisoformat(rows[0]["archived_at"])


def test_archive_note_accepts_null_person_name(db: Memory) -> None:
    archive_note(
        db,
        person_record_id="rec_1",
        person_name=None,
        note="old note",
    )
    with db.lock:
        cur = db._conn.execute("SELECT person_name FROM keep_warm_note_history")
        row = cur.fetchone()
    assert row["person_name"] is None


def test_archive_note_multiple_rows_for_same_person(db: Memory) -> None:
    """Same person gets multiple rows over time."""
    for text in ["first", "second", "third"]:
        archive_note(
            db,
            person_record_id="rec_x",
            person_name="X",
            note=text,
        )
    with db.lock:
        cur = db._conn.execute(
            "SELECT COUNT(*) FROM keep_warm_note_history WHERE person_record_id = ?",
            ("rec_x",),
        )
        assert cur.fetchone()[0] == 3


def test_list_note_history_returns_newest_first(db: Memory) -> None:
    """Rows come back newest-first based on archived_at DESC, ties broken by id DESC."""
    # Fast loop may produce identical archived_at strings; the id DESC tie-break
    # is what actually delivers the newest-first order here. Either path is
    # correct per the ORDER BY.
    for text in ["oldest", "middle", "newest"]:
        archive_note(
            db,
            person_record_id="rec_abc",
            person_name="A",
            note=text,
        )
    rows = list_note_history(db, person_record_id="rec_abc")
    assert [r["note"] for r in rows] == ["newest", "middle", "oldest"]


def test_list_note_history_filters_by_person(db: Memory) -> None:
    archive_note(db, person_record_id="rec_a", person_name="A", note="a1")
    archive_note(db, person_record_id="rec_b", person_name="B", note="b1")
    rows = list_note_history(db, person_record_id="rec_a")
    assert len(rows) == 1
    assert rows[0]["note"] == "a1"


def test_list_note_history_empty_when_no_rows(db: Memory) -> None:
    assert list_note_history(db, person_record_id="never") == []


def test_list_note_history_limit(db: Memory) -> None:
    for i in range(10):
        archive_note(db, person_record_id="rec_l", person_name="L", note=f"n{i}")
    assert len(list_note_history(db, person_record_id="rec_l", limit=3)) == 3
