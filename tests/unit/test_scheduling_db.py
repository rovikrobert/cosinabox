"""Tests for scheduling DB layer."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from cosinabox.memory import Memory
from cosinabox.scheduling import db as sched_db
from cosinabox.scheduling.models import (
    Participant,
    SchedulingRequest,
    SchedulingStatus,
    TimeSlot,
)


@pytest.fixture
def mem(tmp_path):
    return Memory(db_path=tmp_path / "test.db")


@pytest.fixture
def sample_request():
    return SchedulingRequest(
        id="",
        title="Test Sync",
        duration_minutes=30,
        date_range_start=date(2026, 4, 14),
        date_range_end=date(2026, 4, 21),
        preferred_timezone="UTC",
        participants=[
            Participant(name="Alice", email="alice@x.com", timezone="UTC", channel="gmail"),
            Participant(name="Bob", telegram_id="12345", timezone="UTC", channel="telegram"),
        ],
    )


class TestCreateAndGet:
    def test_create_returns_id(self, mem, sample_request):
        rid = sched_db.create_request(mem, sample_request)
        assert rid
        assert len(rid) > 0

    def test_roundtrip(self, mem, sample_request):
        rid = sched_db.create_request(mem, sample_request)
        loaded = sched_db.get_request(mem, rid)
        assert loaded is not None
        assert loaded.title == "Test Sync"
        assert loaded.duration_minutes == 30
        assert len(loaded.participants) == 2
        assert loaded.participants[0].name == "Alice"
        assert loaded.participants[0].db_id is not None

    def test_get_missing_returns_none(self, mem):
        assert sched_db.get_request(mem, "nonexistent") is None


class TestStatusUpdates:
    def test_update_status(self, mem, sample_request):
        rid = sched_db.create_request(mem, sample_request)
        sched_db.update_request_status(mem, rid, SchedulingStatus.POLLING.value)
        loaded = sched_db.get_request(mem, rid)
        assert loaded.status == SchedulingStatus.POLLING.value

    def test_get_active_requests_filtered(self, mem):
        req1 = SchedulingRequest(
            id="r1", title="Active", duration_minutes=30,
            date_range_start=date(2026, 4, 14), date_range_end=date(2026, 4, 21),
        )
        req2 = SchedulingRequest(
            id="r2", title="Cancelled", duration_minutes=30,
            date_range_start=date(2026, 4, 14), date_range_end=date(2026, 4, 21),
            status=SchedulingStatus.CANCELLED.value,
        )
        sched_db.create_request(mem, req1)
        sched_db.create_request(mem, req2)
        # req1 defaults to 'proposing'
        active = sched_db.get_active_requests(
            mem, status_filter=[SchedulingStatus.PROPOSING.value],
        )
        assert len(active) == 1
        assert active[0].id == "r1"


class TestParticipants:
    def test_update_participant_status(self, mem, sample_request):
        rid = sched_db.create_request(mem, sample_request)
        loaded = sched_db.get_request(mem, rid)
        pid = loaded.participants[0].db_id
        sched_db.update_participant_status(
            mem, pid, "sent", gmail_thread_id="thread-1", mark_outreach_sent=True,
        )
        reloaded = sched_db.get_request(mem, rid)
        alice = reloaded.participants[0]
        assert alice.status == "sent"
        sent_at = sched_db.get_participant_outreach_sent_at(mem, pid)
        assert sent_at is not None

    def test_outreach_sent_at_none_initially(self, mem, sample_request):
        rid = sched_db.create_request(mem, sample_request)
        loaded = sched_db.get_request(mem, rid)
        pid = loaded.participants[0].db_id
        assert sched_db.get_participant_outreach_sent_at(mem, pid) is None


class TestSlots:
    def test_add_and_get_slots(self, mem, sample_request):
        rid = sched_db.create_request(mem, sample_request)
        slot1 = TimeSlot(
            start_time=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
            end_time=datetime(2026, 4, 14, 10, 30, tzinfo=UTC),
            score=0.95,
        )
        slot2 = TimeSlot(
            start_time=datetime(2026, 4, 14, 14, 0, tzinfo=UTC),
            end_time=datetime(2026, 4, 14, 14, 30, tzinfo=UTC),
            score=0.75,
        )
        sched_db.add_slot(mem, rid, slot1)
        sched_db.add_slot(mem, rid, slot2)
        slots = sched_db.get_slots(mem, rid)
        assert len(slots) == 2
        # Sorted by score DESC
        assert slots[0].score == 0.95
        assert slots[1].score == 0.75

    def test_approve_slot_move(self, mem, sample_request):
        rid = sched_db.create_request(mem, sample_request)
        slot = TimeSlot(
            start_time=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
            end_time=datetime(2026, 4, 14, 10, 30, tzinfo=UTC),
            requires_move="event-abc",
        )
        slot_id = sched_db.add_slot(mem, rid, slot)
        sched_db.approve_slot_move(mem, slot_id)
        slots = sched_db.get_slots(mem, rid)
        assert slots[0].move_approved is True


class TestResponses:
    def test_record_response(self, mem, sample_request):
        rid = sched_db.create_request(mem, sample_request)
        loaded = sched_db.get_request(mem, rid)
        pid = loaded.participants[0].db_id
        slot = TimeSlot(
            start_time=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
            end_time=datetime(2026, 4, 14, 10, 30, tzinfo=UTC),
        )
        sid = sched_db.add_slot(mem, rid, slot)
        sched_db.record_response(
            mem, request_id=rid, participant_db_id=pid,
            slot_db_id=sid, response="yes",
        )
        responses = sched_db.get_responses(mem, rid)
        assert len(responses) == 1
        assert responses[0]["response"] == "yes"

    def test_invalid_response_raises(self, mem, sample_request):
        rid = sched_db.create_request(mem, sample_request)
        loaded = sched_db.get_request(mem, rid)
        with pytest.raises(ValueError):
            sched_db.record_response(
                mem, request_id=rid,
                participant_db_id=loaded.participants[0].db_id,
                slot_db_id=1, response="maybe",
            )

    def test_record_response_flips_sent_to_responded(self, mem, sample_request):
        rid = sched_db.create_request(mem, sample_request)
        loaded = sched_db.get_request(mem, rid)
        pid = loaded.participants[0].db_id
        sched_db.update_participant_status(mem, pid, "sent")
        slot = TimeSlot(
            start_time=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
            end_time=datetime(2026, 4, 14, 10, 30, tzinfo=UTC),
        )
        sid = sched_db.add_slot(mem, rid, slot)
        sched_db.record_response(
            mem, request_id=rid, participant_db_id=pid,
            slot_db_id=sid, response="yes",
        )
        reloaded = sched_db.get_participants(mem, rid)[0]
        assert reloaded.status == "responded"

    def test_record_response_flips_nudged_to_responded(self, mem, sample_request):
        rid = sched_db.create_request(mem, sample_request)
        loaded = sched_db.get_request(mem, rid)
        pid = loaded.participants[0].db_id
        sched_db.update_participant_status(mem, pid, "nudged")
        slot = TimeSlot(
            start_time=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
            end_time=datetime(2026, 4, 14, 10, 30, tzinfo=UTC),
        )
        sid = sched_db.add_slot(mem, rid, slot)
        sched_db.record_response(
            mem, request_id=rid, participant_db_id=pid,
            slot_db_id=sid, response="yes",
        )
        reloaded = sched_db.get_participants(mem, rid)[0]
        assert reloaded.status == "responded"

    def test_record_response_does_not_resurrect_no_response(self, mem, sample_request):
        rid = sched_db.create_request(mem, sample_request)
        loaded = sched_db.get_request(mem, rid)
        pid = loaded.participants[0].db_id
        sched_db.update_participant_status(mem, pid, "no_response")
        slot = TimeSlot(
            start_time=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
            end_time=datetime(2026, 4, 14, 10, 30, tzinfo=UTC),
        )
        sid = sched_db.add_slot(mem, rid, slot)
        sched_db.record_response(
            mem, request_id=rid, participant_db_id=pid,
            slot_db_id=sid, response="yes",
        )
        reloaded = sched_db.get_participants(mem, rid)[0]
        assert reloaded.status == "no_response"


class TestGuardedStatusUpdate:
    def test_guarded_update_success(self, mem, sample_request):
        rid = sched_db.create_request(mem, sample_request)
        sched_db.update_request_status(mem, rid, SchedulingStatus.POLLING.value)
        ok = sched_db.update_request_status_guarded(
            mem, rid, SchedulingStatus.POLLING.value,
            SchedulingStatus.CONVERGED.value,
        )
        assert ok is True
        assert sched_db.get_request(mem, rid).status == SchedulingStatus.CONVERGED.value

    def test_guarded_update_stale_expected(self, mem, sample_request):
        rid = sched_db.create_request(mem, sample_request)
        sched_db.update_request_status(mem, rid, SchedulingStatus.POLLING.value)
        # First one wins
        assert sched_db.update_request_status_guarded(
            mem, rid, SchedulingStatus.POLLING.value,
            SchedulingStatus.CONVERGED.value,
        )
        # Second, racing from stale POLLING, fails
        ok = sched_db.update_request_status_guarded(
            mem, rid, SchedulingStatus.POLLING.value,
            SchedulingStatus.CANCELLED.value,
        )
        assert ok is False
        # Status preserved
        assert sched_db.get_request(mem, rid).status == SchedulingStatus.CONVERGED.value


class TestTransitionOptimisticConcurrency:
    def test_transition_raises_invalid_transition_on_stale_from(self, mem, sample_request):
        from cosinabox.scheduling.coordinator import InvalidTransition, transition

        rid = sched_db.create_request(mem, sample_request)
        sched_db.update_request_status(mem, rid, SchedulingStatus.POLLING.value)

        # Thread A wins
        transition(mem, rid, SchedulingStatus.POLLING, SchedulingStatus.CONVERGED)

        # Thread B loses — tries POLLING→CANCELLED but DB is already CONVERGED
        with pytest.raises(InvalidTransition):
            transition(mem, rid, SchedulingStatus.POLLING, SchedulingStatus.CANCELLED)
        assert sched_db.get_request(mem, rid).status == SchedulingStatus.CONVERGED.value


class TestIntegrityConstraints:
    def test_invalid_status_raises_scheduling_error(self, mem, sample_request):
        from cosinabox.scheduling.models import SchedulingStateError

        rid = sched_db.create_request(mem, sample_request)
        with pytest.raises(SchedulingStateError):
            sched_db.update_request_status(mem, rid, "not_a_real_status")

    def test_foreign_key_enforcement(self, mem):
        import sqlite3
        # Try to insert a participant referencing a nonexistent request
        with pytest.raises(sqlite3.IntegrityError):
            mem._conn.execute(
                """INSERT INTO scheduling_participants
                   (request_id, name, timezone, channel, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("nonexistent-req", "Ghost", "UTC", "gmail", "pending",
                 datetime.now(UTC).isoformat()),
            )
            mem._conn.commit()


class TestMoves:
    def test_record_and_undo_move(self, mem, sample_request):
        rid = sched_db.create_request(mem, sample_request)
        now = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
        move_id = sched_db.record_move(
            mem, request_id=rid, event_id="event-1",
            original_start=now, original_end=now + timedelta(minutes=30),
            new_start=now + timedelta(hours=2),
            new_end=now + timedelta(hours=2, minutes=30),
        )
        assert move_id > 0
        sched_db.mark_move_undone(mem, move_id)
        cur = mem._conn.execute("SELECT undone FROM scheduling_moves WHERE id = ?", (move_id,))
        assert cur.fetchone()[0] == 1
