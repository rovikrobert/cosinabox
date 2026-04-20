# ruff: noqa: I001
"""CRUD tests for the commitments package.

Ported from cos-agent's commitments.py, translated to sync + SQLite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cosinabox.commitments import (
    CommitmentAlreadyClosed,
    CommitmentNotClosed,
    CommitmentNotFound,
    CommitmentStatus,
    close_commitment,
    create_commitment,
    dismiss_commitment,
    get_commitment,
    list_commitments,
    list_recent_closures,
    reopen_commitment,
    update_commitment,
)
from cosinabox.memory import Memory


@pytest.fixture
def db(tmp_path: Path) -> Memory:
    return Memory(db_path=tmp_path / "test.db")


# ---------------------------------------------------------------------------
# create + list
# ---------------------------------------------------------------------------


def test_create_and_list_single_item(db: Memory) -> None:
    c = create_commitment(db, title="Send Sarah Q3 deck", priority=1)
    assert c["id"] > 0
    assert c["title"] == "Send Sarah Q3 deck"
    assert c["status"] == "open"
    assert c["priority"] == 1
    assert c["owner"] == "user"

    items = list_commitments(db)
    assert len(items) == 1
    assert items[0]["id"] == c["id"]


def test_list_defaults_to_open_only(db: Memory) -> None:
    a = create_commitment(db, title="open one")
    b = create_commitment(db, title="will close")
    close_commitment(db, b["id"], reason="resolved on the call")

    open_items = list_commitments(db)
    assert [c["id"] for c in open_items] == [a["id"]]


def test_list_with_status_filter(db: Memory) -> None:
    a = create_commitment(db, title="a")
    update_commitment(db, a["id"], status=CommitmentStatus.IN_PROGRESS.value)
    create_commitment(db, title="b")

    in_progress = list_commitments(db, status_filter=["in_progress"])
    open_only = list_commitments(db, status_filter=["open"])

    assert [c["title"] for c in in_progress] == ["a"]
    assert [c["title"] for c in open_only] == ["b"]


def test_list_respects_limit(db: Memory) -> None:
    for i in range(5):
        create_commitment(db, title=f"item {i}")
    assert len(list_commitments(db, limit=3)) == 3


# ---------------------------------------------------------------------------
# get + update
# ---------------------------------------------------------------------------


def test_get_returns_full_row(db: Memory) -> None:
    c = create_commitment(
        db,
        title="ship v1",
        stakeholder="Sarah Chen",
        priority=2,
        workstream="engine",
        description="Cut the 0.2 release.",
    )
    got = get_commitment(db, c["id"])
    assert got["title"] == "ship v1"
    assert got["stakeholder"] == "Sarah Chen"
    assert got["workstream"] == "engine"
    assert got["description"] == "Cut the 0.2 release."


def test_get_missing_raises(db: Memory) -> None:
    with pytest.raises(CommitmentNotFound):
        get_commitment(db, 9999)


def test_update_status_and_priority(db: Memory) -> None:
    c = create_commitment(db, title="x")
    update_commitment(db, c["id"], status="blocked", priority=5)
    got = get_commitment(db, c["id"])
    assert got["status"] == "blocked"
    assert got["priority"] == 5


def test_update_ignores_unknown_fields(db: Memory) -> None:
    c = create_commitment(db, title="x")
    update_commitment(db, c["id"], title="naughty", not_a_field="hello")  # type: ignore[call-arg]
    got = get_commitment(db, c["id"])
    # Whitelist enforces: title NOT updatable via update_commitment; use
    # a dedicated rename API if needed. `not_a_field` silently dropped.
    assert got["title"] == "x"


def test_update_missing_raises(db: Memory) -> None:
    with pytest.raises(CommitmentNotFound):
        update_commitment(db, 9999, status="done")


# ---------------------------------------------------------------------------
# close / reopen / dismiss
# ---------------------------------------------------------------------------


def test_close_flips_status_and_logs_closure(db: Memory) -> None:
    c = create_commitment(db, title="ship")
    close_commitment(db, c["id"], reason="merged PR #42")

    got = get_commitment(db, c["id"])
    assert got["status"] == "done"

    closures = list_recent_closures(db, limit=10)
    assert len(closures) == 1
    assert closures[0]["commitment_id"] == c["id"]
    assert closures[0]["verb"] == "close"
    assert closures[0]["reason"] == "merged PR #42"


def test_dismiss_marks_cancelled(db: Memory) -> None:
    c = create_commitment(db, title="maybe do this")
    dismiss_commitment(db, c["id"], reason="priorities changed")

    got = get_commitment(db, c["id"])
    assert got["status"] == "cancelled"
    closures = list_recent_closures(db, limit=10)
    assert closures[0]["verb"] == "dismiss"


def test_close_already_closed_raises(db: Memory) -> None:
    c = create_commitment(db, title="x")
    close_commitment(db, c["id"])
    with pytest.raises(CommitmentAlreadyClosed):
        close_commitment(db, c["id"])


def test_dismiss_already_closed_raises(db: Memory) -> None:
    c = create_commitment(db, title="x")
    close_commitment(db, c["id"])
    with pytest.raises(CommitmentAlreadyClosed):
        dismiss_commitment(db, c["id"])


def test_reopen_restores_open(db: Memory) -> None:
    c = create_commitment(db, title="x")
    close_commitment(db, c["id"])
    reopen_commitment(db, c["id"])
    assert get_commitment(db, c["id"])["status"] == "open"


def test_reopen_not_closed_raises(db: Memory) -> None:
    c = create_commitment(db, title="x")
    with pytest.raises(CommitmentNotClosed):
        reopen_commitment(db, c["id"])


# ---------------------------------------------------------------------------
# constraints
# ---------------------------------------------------------------------------


def test_priority_out_of_range_is_clamped(db: Memory) -> None:
    lo = create_commitment(db, title="lo", priority=-1)
    hi = create_commitment(db, title="hi", priority=99)
    assert get_commitment(db, lo["id"])["priority"] == 1
    assert get_commitment(db, hi["id"])["priority"] == 5


def test_unknown_source_falls_back_to_manual(db: Memory) -> None:
    c = create_commitment(db, title="x", source="not_a_source")
    assert get_commitment(db, c["id"])["source"] == "manual"


def test_deadline_accepts_iso_date_string(db: Memory) -> None:
    c = create_commitment(db, title="x", deadline="2026-05-01")
    assert get_commitment(db, c["id"])["deadline"] == "2026-05-01"
