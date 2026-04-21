"""SQLite CRUD for commitments. Sync, operates on a ``Memory`` instance.

Returns plain dicts by default so the output can be injected into
briefing prompts without extra serialization.
"""

from __future__ import annotations

from typing import Any

from cosinabox.commitments.models import (
    TERMINAL_STATUSES,
    UPDATABLE_FIELDS,
    VALID_SOURCES,
    CommitmentAlreadyClosed,
    CommitmentNotClosed,
    CommitmentNotFound,
    CommitmentStatus,
)
from cosinabox.memory import Memory
from cosinabox.memory._util import now_iso


def _row_to_dict(row: Any) -> dict[str, Any]:
    """sqlite3.Row → plain dict so callers can serialize freely."""
    return dict(row)


def create_commitment(
    db: Memory,
    *,
    title: str,
    owner: str = "user",
    priority: int = 3,
    deadline: str | None = None,
    source: str = "manual",
    source_ref: str | None = None,
    stakeholder: str | None = None,
    description: str | None = None,
    workstream: str | None = None,
) -> dict[str, Any]:
    """Create a new commitment. Returns the created row as a dict."""
    clamped_priority = max(1, min(5, priority))
    safe_source = source if source in VALID_SOURCES else "manual"

    ts = now_iso()
    # Serialize against other threads on the same SQLite connection.
    # Without this, concurrent APScheduler + Telegram + SubAgent writes
    # can corrupt cursor state → sqlite3.InterfaceError.
    with db.lock:
        cur = db._conn.execute(
            """INSERT INTO commitments
               (title, description, owner, priority, deadline, source, source_ref,
                stakeholder, workstream, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                title,
                description,
                owner,
                clamped_priority,
                deadline,
                safe_source,
                source_ref,
                stakeholder,
                workstream,
                ts,
                ts,
            ),
        )
        db._conn.commit()
        new_id = cur.lastrowid
        assert new_id is not None
        return get_commitment(db, new_id)


def get_commitment(db: Memory, commitment_id: int) -> dict[str, Any]:
    """Return a single commitment as a dict. Raises CommitmentNotFound."""
    with db.lock:
        cur = db._conn.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,))
        row = cur.fetchone()
    if row is None:
        raise CommitmentNotFound(f"#{commitment_id}")
    return _row_to_dict(row)


def list_commitments(
    db: Memory,
    *,
    status_filter: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List commitments. Defaults to open items.

    Sorted by (priority ASC, deadline ASC nulls last, id ASC). Priority 1
    is highest — we surface urgent items first regardless of insertion
    order.
    """
    if status_filter is None:
        status_filter = [CommitmentStatus.OPEN.value]

    placeholders = ",".join("?" * len(status_filter))
    query = (
        f"SELECT * FROM commitments WHERE status IN ({placeholders}) "
        "ORDER BY priority ASC, "
        "CASE WHEN deadline IS NULL THEN 1 ELSE 0 END, "
        "deadline ASC, id ASC LIMIT ?"
    )
    with db.lock:
        cur = db._conn.execute(query, (*status_filter, limit))
        rows = cur.fetchall()
    return [_row_to_dict(row) for row in rows]


def update_commitment(
    db: Memory,
    commitment_id: int,
    **fields: Any,
) -> dict[str, Any]:
    """Update whitelisted fields in-place. Returns the refreshed row.

    Only fields listed in ``UPDATABLE_FIELDS`` are applied; anything else
    (including ``title`` and ``source``, which are set at creation) is
    silently ignored.
    """
    # Existence first — raises CommitmentNotFound if absent.
    get_commitment(db, commitment_id)

    changes = {k: v for k, v in fields.items() if k in UPDATABLE_FIELDS}
    if changes:
        if "priority" in changes and changes["priority"] is not None:
            changes["priority"] = max(1, min(5, int(changes["priority"])))
        set_clause = ", ".join(f"{k} = ?" for k in changes)
        values = [*changes.values(), now_iso(), commitment_id]
        with db.lock:
            db._conn.execute(
                f"UPDATE commitments SET {set_clause}, updated_at = ? WHERE id = ?",
                values,
            )
            db._conn.commit()
    return get_commitment(db, commitment_id)


def close_commitment(
    db: Memory,
    commitment_id: int,
    *,
    reason: str | None = None,
    closed_by: str = "user",
) -> dict[str, Any]:
    """Close a commitment (status → done) and log to manual_closures.

    Raises CommitmentAlreadyClosed if the commitment is already in a
    terminal state.
    """
    current = get_commitment(db, commitment_id)
    if current["status"] in TERMINAL_STATUSES:
        raise CommitmentAlreadyClosed(f"#{commitment_id} already {current['status']}")

    ts = now_iso()
    with db.lock:
        db._conn.execute(
            "UPDATE commitments SET status = ?, updated_at = ? WHERE id = ?",
            (CommitmentStatus.DONE.value, ts, commitment_id),
        )
        db._conn.execute(
            "INSERT INTO manual_closures "
            "(commitment_id, verb, reason, closed_at, closed_by) "
            "VALUES (?, 'close', ?, ?, ?)",
            (commitment_id, reason, ts, closed_by),
        )
        db._conn.commit()
    return get_commitment(db, commitment_id)


def dismiss_commitment(
    db: Memory,
    commitment_id: int,
    *,
    reason: str | None = None,
    closed_by: str = "user",
) -> dict[str, Any]:
    """Dismiss a commitment (status → cancelled) and log a 'dismiss' closure."""
    current = get_commitment(db, commitment_id)
    if current["status"] in TERMINAL_STATUSES:
        raise CommitmentAlreadyClosed(f"#{commitment_id} already {current['status']}")

    ts = now_iso()
    with db.lock:
        db._conn.execute(
            "UPDATE commitments SET status = ?, updated_at = ? WHERE id = ?",
            (CommitmentStatus.CANCELLED.value, ts, commitment_id),
        )
        db._conn.execute(
            "INSERT INTO manual_closures "
            "(commitment_id, verb, reason, closed_at, closed_by) "
            "VALUES (?, 'dismiss', ?, ?, ?)",
            (commitment_id, reason, ts, closed_by),
        )
        db._conn.commit()
    return get_commitment(db, commitment_id)


def reopen_commitment(
    db: Memory,
    commitment_id: int,
) -> dict[str, Any]:
    """Reopen a closed commitment. Raises CommitmentNotClosed if not terminal."""
    current = get_commitment(db, commitment_id)
    if current["status"] not in TERMINAL_STATUSES:
        raise CommitmentNotClosed(f"#{commitment_id} is {current['status']}, not closed")
    with db.lock:
        db._conn.execute(
            "UPDATE commitments SET status = ?, updated_at = ? WHERE id = ?",
            (CommitmentStatus.OPEN.value, now_iso(), commitment_id),
        )
        db._conn.commit()
    return get_commitment(db, commitment_id)


def list_recent_closures(
    db: Memory,
    *,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Return the most recent manual_closures rows (for audit views)."""
    with db.lock:
        cur = db._conn.execute(
            "SELECT * FROM manual_closures ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
    return [_row_to_dict(row) for row in rows]
