"""CRUD for keep_warm_note_history.

Free functions operating on a ``Memory`` instance. Matches the
``commitments/store.py`` pattern (sync, dict returns, connection lock).
"""

from __future__ import annotations

from datetime import UTC, datetime

from cosinabox.memory import Memory


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


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
            (person_record_id, person_name, note, _now_iso(), reason),
        )
        db._conn.commit()
