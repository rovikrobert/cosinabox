"""Sync SQLite CRUD for group scheduling tables.

Ported from cos-agent/src/scheduling/db.py, converted async→sync.
Uses the Memory class's sqlite3 connection (WAL mode, thread-safe).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

import sqlite3

from cosinabox.scheduling.models import (
    Participant,
    SchedulingRequest,
    SchedulingStateError,
    SchedulingStatus,
    TimeSlot,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scheduling requests
# ---------------------------------------------------------------------------

def create_request(db: Any, req: SchedulingRequest) -> str:
    """Insert a scheduling request and its participants. Returns the request id."""
    req_id = req.id or uuid.uuid4().hex
    now = datetime.now(UTC).isoformat()

    db._conn.execute(
        """INSERT INTO scheduling_requests
           (id, title, duration_minutes, requested_by, date_range_start,
            date_range_end, status, preferred_timezone, notes,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            req_id, req.title, req.duration_minutes, "owner",
            req.date_range_start.isoformat(), req.date_range_end.isoformat(),
            req.status, req.preferred_timezone, req.notes, now, now,
        ),
    )

    for p in req.participants:
        cur = db._conn.execute(
            """INSERT INTO scheduling_participants
               (request_id, name, email, telegram_id, timezone, channel, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (req_id, p.name, p.email, p.telegram_id, p.timezone, p.channel, p.status, now),
        )
        p.db_id = cur.lastrowid

    db._conn.commit()
    logger.info("Created scheduling request %s: %s", req_id, req.title)
    return req_id


def get_request(db: Any, request_id: str) -> SchedulingRequest | None:
    """Load a scheduling request with its participants and slots."""
    cur = db._conn.execute(
        "SELECT * FROM scheduling_requests WHERE id = ?", (request_id,),
    )
    row = cur.fetchone()
    if not row:
        return None

    participants = get_participants(db, request_id)
    slots = get_slots(db, request_id)

    return SchedulingRequest(
        id=row["id"],
        title=row["title"],
        duration_minutes=row["duration_minutes"],
        participants=participants,
        date_range_start=date.fromisoformat(row["date_range_start"]),
        date_range_end=date.fromisoformat(row["date_range_end"]),
        status=row["status"],
        preferred_timezone=row["preferred_timezone"] or "UTC",
        notes=row["notes"],
        slots=slots,
    )


def update_request_status(db: Any, request_id: str, status: str) -> None:
    """Transition a request to a new status. Raises SchedulingStateError on bad status."""
    now = datetime.now(UTC).isoformat()
    try:
        db._conn.execute(
            "UPDATE scheduling_requests SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, request_id),
        )
        db._conn.commit()
    except sqlite3.IntegrityError as exc:
        raise SchedulingStateError(f"Invalid status '{status}': {exc}") from exc


def get_active_requests(
    db: Any, *, status_filter: list[str] | None = None,
) -> list[SchedulingRequest]:
    """Get all requests, optionally filtered by status."""
    if status_filter:
        placeholders = ",".join("?" * len(status_filter))
        cur = db._conn.execute(
            f"SELECT id FROM scheduling_requests WHERE status IN ({placeholders})",
            status_filter,
        )
    else:
        cur = db._conn.execute("SELECT id FROM scheduling_requests")

    ids = [r["id"] for r in cur.fetchall()]
    requests = []
    for rid in ids:
        req = get_request(db, rid)
        if req:
            requests.append(req)
    return requests


# ---------------------------------------------------------------------------
# Participants
# ---------------------------------------------------------------------------

def get_participant_by_db_id(db: Any, participant_db_id: int) -> Participant | None:
    cur = db._conn.execute(
        "SELECT * FROM scheduling_participants WHERE id = ?",
        (participant_db_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    return Participant(
        name=row["name"],
        email=row["email"],
        telegram_id=row["telegram_id"],
        timezone=row["timezone"],
        channel=row["channel"],
        db_id=row["id"],
        status=row["status"],
    )


def get_slot_ids_for_request(db: Any, request_id: str) -> set[int]:
    cur = db._conn.execute(
        "SELECT id FROM scheduling_slots WHERE request_id = ?",
        (request_id,),
    )
    return {row["id"] for row in cur.fetchall()}


def get_participants(db: Any, request_id: str) -> list[Participant]:
    cur = db._conn.execute(
        "SELECT * FROM scheduling_participants WHERE request_id = ? ORDER BY id",
        (request_id,),
    )
    return [
        Participant(
            name=row["name"],
            email=row["email"],
            telegram_id=row["telegram_id"],
            timezone=row["timezone"],
            channel=row["channel"],
            db_id=row["id"],
            status=row["status"],
        )
        for row in cur.fetchall()
    ]


def update_participant_status(
    db: Any, participant_db_id: int, status: str,
    *, gmail_thread_id: str | None = None,
    gmail_draft_id: str | None = None,
    mark_outreach_sent: bool = False,
) -> None:
    updates = ["status = ?"]
    params: list[Any] = [status]
    if gmail_thread_id is not None:
        updates.append("gmail_thread_id = ?")
        params.append(gmail_thread_id)
    if gmail_draft_id is not None:
        updates.append("gmail_draft_id = ?")
        params.append(gmail_draft_id)
    if mark_outreach_sent:
        updates.append("outreach_sent_at = ?")
        params.append(datetime.now(UTC).isoformat())
    params.append(participant_db_id)

    db._conn.execute(
        f"UPDATE scheduling_participants SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    db._conn.commit()


def get_participant_outreach_sent_at(
    db: Any, participant_db_id: int,
) -> datetime | None:
    cur = db._conn.execute(
        "SELECT outreach_sent_at FROM scheduling_participants WHERE id = ?",
        (participant_db_id,),
    )
    row = cur.fetchone()
    if not row or not row["outreach_sent_at"]:
        return None
    return datetime.fromisoformat(row["outreach_sent_at"])


# ---------------------------------------------------------------------------
# Slots
# ---------------------------------------------------------------------------

def add_slot(db: Any, request_id: str, slot: TimeSlot) -> int:
    now = datetime.now(UTC).isoformat()
    cur = db._conn.execute(
        """INSERT INTO scheduling_slots
           (request_id, start_time, end_time, score, requires_move, move_approved, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            request_id, slot.start_time.isoformat(), slot.end_time.isoformat(),
            slot.score, slot.requires_move, int(slot.move_approved), now,
        ),
    )
    db._conn.commit()
    slot_id = cur.lastrowid or 0
    slot.db_id = slot_id
    return slot_id


def get_slots(db: Any, request_id: str) -> list[TimeSlot]:
    cur = db._conn.execute(
        "SELECT * FROM scheduling_slots WHERE request_id = ? ORDER BY score DESC",
        (request_id,),
    )
    return [
        TimeSlot(
            start_time=datetime.fromisoformat(row["start_time"]),
            end_time=datetime.fromisoformat(row["end_time"]),
            score=row["score"],
            requires_move=row["requires_move"],
            move_approved=bool(row["move_approved"]),
            db_id=row["id"],
        )
        for row in cur.fetchall()
    ]


def approve_slot_move(db: Any, slot_db_id: int) -> None:
    db._conn.execute(
        "UPDATE scheduling_slots SET move_approved = 1 WHERE id = ?", (slot_db_id,),
    )
    db._conn.commit()


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

def record_response(
    db: Any, *, request_id: str, participant_db_id: int,
    slot_db_id: int, response: str,
) -> None:
    if response not in ("yes", "if_needed", "no"):
        raise ValueError(f"Invalid response: {response}")
    now = datetime.now(UTC).isoformat()
    db._conn.execute(
        """INSERT INTO scheduling_responses
           (request_id, participant_id, slot_id, response, responded_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(request_id, participant_id, slot_id)
           DO UPDATE SET response=excluded.response, responded_at=excluded.responded_at""",
        (request_id, participant_db_id, slot_db_id, response, now),
    )
    db._conn.commit()


def get_responses(db: Any, request_id: str) -> list[dict[str, Any]]:
    cur = db._conn.execute(
        "SELECT * FROM scheduling_responses WHERE request_id = ?", (request_id,),
    )
    return [dict(row) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Moves (undo log)
# ---------------------------------------------------------------------------

def record_move(
    db: Any, *, request_id: str, event_id: str,
    original_start: datetime, original_end: datetime,
    new_start: datetime, new_end: datetime,
) -> int:
    now = datetime.now(UTC).isoformat()
    cur = db._conn.execute(
        """INSERT INTO scheduling_moves
           (request_id, event_id, original_start, original_end,
            new_start, new_end, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            request_id, event_id,
            original_start.isoformat(), original_end.isoformat(),
            new_start.isoformat(), new_end.isoformat(), now,
        ),
    )
    db._conn.commit()
    return cur.lastrowid or 0


def mark_move_undone(db: Any, move_id: int) -> None:
    db._conn.execute(
        "UPDATE scheduling_moves SET undone = 1 WHERE id = ?", (move_id,),
    )
    db._conn.commit()
