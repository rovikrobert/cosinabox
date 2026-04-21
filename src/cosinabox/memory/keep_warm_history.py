"""CRUD for keep_warm_note_history.

Free functions operating on a ``Memory`` instance. Matches the
``commitments/store.py`` pattern (sync, dict returns, connection lock).
"""

from __future__ import annotations

from typing import Any

from cosinabox.memory import Memory
from cosinabox.memory._util import now_iso


def archive_note(
    db: Memory,
    *,
    person_record_id: str,
    person_name: str | None,
    note: str,
    reason: str | None = None,
) -> None:
    """Insert one history row for a keep-warm note being overwritten.

    ``note`` is the PRIOR value being preserved — not the incoming one.
    ``reason`` is free-text context; today every archival is called from
    the set_keep_warm handler and passes None (placeholder for future use).
    """
    with db.lock:
        db._conn.execute(
            "INSERT INTO keep_warm_note_history "
            "(person_record_id, person_name, note, archived_at, reason) "
            "VALUES (?, ?, ?, ?, ?)",
            (person_record_id, person_name, note, now_iso(), reason),
        )
        db._conn.commit()


def list_note_history(
    db: Memory,
    *,
    person_record_id: str,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Return archived notes for a person, newest first.

    Ties (same ``archived_at`` ISO string) are broken by ``id DESC``.
    """
    with db.lock:
        cur = db._conn.execute(
            "SELECT id, person_record_id, person_name, note, archived_at, reason "
            "FROM keep_warm_note_history "
            "WHERE person_record_id = ? "
            "ORDER BY archived_at DESC, id DESC LIMIT ?",
            (person_record_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]
