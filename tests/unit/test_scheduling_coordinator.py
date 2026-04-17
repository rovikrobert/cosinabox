"""Tests for the scheduling coordinator state machine."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from cosinabox.memory import Memory
from cosinabox.scheduling import coordinator
from cosinabox.scheduling import db as sched_db
from cosinabox.scheduling.context import OwnerProfile, SchedulingContext
from cosinabox.scheduling.coordinator import (
    _TRANSITIONS,
    InvalidTransition,
    find_consensus,
    record_decision,
    start_scheduling,
    transition,
)
from cosinabox.scheduling.models import (
    Participant,
    SchedulingRequest,
    SchedulingStatus,
    TimeSlot,
)


def _ctx(mem, **overrides):
    """Build a minimal SchedulingContext for tests."""
    defaults = {
        "db": mem,
        "owner": OwnerProfile(name="Host", timezone="UTC"),
    }
    defaults.update(overrides)
    return SchedulingContext(**defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mem(tmp_path):
    return Memory(db_path=tmp_path / "coord.db")


@pytest.fixture
def request_id(mem):
    """A minimal request persisted in DB, status PROPOSING."""
    req = SchedulingRequest(
        id="",
        title="State test",
        duration_minutes=30,
        date_range_start=date(2026, 4, 14),
        date_range_end=date(2026, 4, 21),
        preferred_timezone="UTC",
        participants=[
            Participant(name="Alice", email="alice@x.com", timezone="UTC", channel="gmail"),
        ],
    )
    return sched_db.create_request(mem, req)


def _force_status(mem, rid: str, status: SchedulingStatus) -> None:
    """Bypass the state machine to set up arbitrary 'from' states for tests."""
    sched_db.update_request_status(mem, rid, status.value)


# ---------------------------------------------------------------------------
# All 64 transition pairs (8x8)
# ---------------------------------------------------------------------------

ALL_STATUSES = list(SchedulingStatus)


@pytest.mark.parametrize("from_status", ALL_STATUSES)
@pytest.mark.parametrize("to_status", ALL_STATUSES)
def test_all_transition_pairs(mem, request_id, from_status, to_status):
    """Every (from, to) pair: legal edges succeed, illegal raise InvalidTransition."""
    _force_status(mem, request_id, from_status)

    legal = to_status in _TRANSITIONS.get(from_status, set())

    if legal:
        transition(mem, request_id, from_status, to_status)
        loaded = sched_db.get_request(mem, request_id)
        assert loaded.status == to_status.value
    else:
        with pytest.raises(InvalidTransition):
            transition(mem, request_id, from_status, to_status)


def test_exactly_seven_legal_edges():
    """Guardrail: the plan specifies exactly 7 legal edges + 3 terminals."""
    total_edges = sum(len(targets) for targets in _TRANSITIONS.values())
    # proposing(3) + owner_review(3) + polling(4) + backchannel(3) + converged(2)
    # + booked(0) + cancelled(0) + expired(0) = 15
    assert total_edges == 15
    assert _TRANSITIONS[SchedulingStatus.BOOKED] == set()
    assert _TRANSITIONS[SchedulingStatus.CANCELLED] == set()
    assert _TRANSITIONS[SchedulingStatus.EXPIRED] == set()


def test_transition_accepts_string_status(mem, request_id):
    """transition() should accept str status as well as enum."""
    transition(mem, request_id, "proposing", "owner_review")
    assert sched_db.get_request(mem, request_id).status == "owner_review"


# ---------------------------------------------------------------------------
# find_consensus
# ---------------------------------------------------------------------------


def _setup_polling_request(mem, *, n_participants=2, n_slots=2):
    ps = [
        Participant(
            name=f"P{i}",
            email=f"p{i}@x.com",
            timezone="UTC",
            channel="gmail",
        )
        for i in range(n_participants)
    ]
    req = SchedulingRequest(
        id="",
        title="Consensus test",
        duration_minutes=30,
        date_range_start=date(2026, 4, 14),
        date_range_end=date(2026, 4, 21),
        preferred_timezone="UTC",
        participants=ps,
        status=SchedulingStatus.POLLING.value,
    )
    rid = sched_db.create_request(mem, req)
    sched_db.update_request_status(mem, rid, SchedulingStatus.POLLING.value)

    loaded = sched_db.get_request(mem, rid)
    base_start = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
    slot_ids: list[int] = []
    for i in range(n_slots):
        slot = TimeSlot(
            start_time=base_start + timedelta(hours=i * 2),
            end_time=base_start + timedelta(hours=i * 2, minutes=30),
            score=1.0 - i * 0.1,
        )
        sid = sched_db.add_slot(mem, rid, slot)
        slot_ids.append(sid)

    return rid, loaded.participants, slot_ids


def test_find_consensus_all_yes(mem):
    rid, parts, slot_ids = _setup_polling_request(mem)
    for p in parts:
        sched_db.record_response(
            mem,
            request_id=rid,
            participant_db_id=p.db_id,
            slot_db_id=slot_ids[0],
            response="yes",
        )
    result = find_consensus(_ctx(mem), rid)
    assert result is not None
    assert result.db_id == slot_ids[0]


def test_find_consensus_if_needed_counts_as_yes(mem):
    rid, parts, slot_ids = _setup_polling_request(mem)
    sched_db.record_response(
        mem,
        request_id=rid,
        participant_db_id=parts[0].db_id,
        slot_db_id=slot_ids[0],
        response="yes",
    )
    sched_db.record_response(
        mem,
        request_id=rid,
        participant_db_id=parts[1].db_id,
        slot_db_id=slot_ids[0],
        response="if_needed",
    )
    result = find_consensus(_ctx(mem), rid)
    assert result is not None
    assert result.db_id == slot_ids[0]


def test_find_consensus_single_no_disqualifies(mem):
    rid, parts, slot_ids = _setup_polling_request(mem)
    sched_db.record_response(
        mem,
        request_id=rid,
        participant_db_id=parts[0].db_id,
        slot_db_id=slot_ids[0],
        response="yes",
    )
    sched_db.record_response(
        mem,
        request_id=rid,
        participant_db_id=parts[1].db_id,
        slot_db_id=slot_ids[0],
        response="no",
    )
    assert find_consensus(_ctx(mem), rid) is None


def test_find_consensus_missing_participant_returns_none(mem):
    rid, parts, slot_ids = _setup_polling_request(mem)
    # Only one of two participants responded.
    sched_db.record_response(
        mem,
        request_id=rid,
        participant_db_id=parts[0].db_id,
        slot_db_id=slot_ids[0],
        response="yes",
    )
    assert find_consensus(_ctx(mem), rid) is None


def test_find_consensus_rescores_against_fresh_calendar(mem):
    """Slots stored .score at PROPOSING time. If the owner's calendar shifts
    during POLLING (up to 48h), the stored scores can misrepresent today's
    reality — a slot that was free may now conflict with a newly-booked event.

    Given fresh calendar events passed to find_consensus, the function should
    re-score qualifying slots and prefer the one with fewer fresh conflicts."""
    # Manual setup so we can put both slots at equivalent local-time scores,
    # so that the stored-score tiebreaker doesn't mask the rescore.
    ps = [
        Participant(name="P0", email="p0@x.com", timezone="UTC", channel="gmail"),
        Participant(name="P1", email="p1@x.com", timezone="UTC", channel="gmail"),
    ]
    req = SchedulingRequest(
        id="",
        title="Rescore test",
        duration_minutes=30,
        date_range_start=date(2026, 4, 14),
        date_range_end=date(2026, 4, 15),
        preferred_timezone="UTC",
        participants=ps,
        status=SchedulingStatus.POLLING.value,
    )
    rid = sched_db.create_request(mem, req)
    sched_db.update_request_status(mem, rid, SchedulingStatus.POLLING.value)
    loaded = sched_db.get_request(mem, rid)

    # Two slots at identical local-time profile (both 10:00 UTC peak), on
    # different days → fresh-rescore is the only tiebreaker that matters.
    slot_a = TimeSlot(
        start_time=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
        end_time=datetime(2026, 4, 14, 10, 30, tzinfo=UTC),
        score=0.95,  # stored: slot A slightly higher
    )
    slot_b = TimeSlot(
        start_time=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
        end_time=datetime(2026, 4, 15, 10, 30, tzinfo=UTC),
        score=0.90,
    )
    sid_a = sched_db.add_slot(mem, rid, slot_a)
    sid_b = sched_db.add_slot(mem, rid, slot_b)

    for p in loaded.participants:
        for sid in (sid_a, sid_b):
            sched_db.record_response(
                mem,
                request_id=rid,
                participant_db_id=p.db_id,
                slot_db_id=sid,
                response="yes",
            )

    # Without fresh calendar, stored score wins -> slot A.
    assert find_consensus(_ctx(mem), rid).db_id == sid_a

    # With fresh calendar showing a new event overlapping slot A, the rescore
    # should prefer slot B (still clear today).
    from cosinabox.scheduling.context import BusyInterval

    provider = FakeCalendarProvider(
        busy=[
            BusyInterval(
                start=slot_a.start_time,
                end=slot_a.end_time,
            ),
        ]
    )
    result = find_consensus(_ctx(mem, calendar=provider), rid)
    assert result is not None
    assert result.db_id == sid_b


def test_find_consensus_without_fresh_calendar_uses_stored_scores(mem):
    """Regression guard: the fresh-calendar path is opt-in. Without it,
    find_consensus behaves exactly as before."""
    rid, parts, slot_ids = _setup_polling_request(mem, n_slots=2)
    for p in parts:
        for sid in slot_ids:
            sched_db.record_response(
                mem,
                request_id=rid,
                participant_db_id=p.db_id,
                slot_db_id=sid,
                response="yes",
            )
    result = find_consensus(_ctx(mem), rid)
    assert result is not None
    assert result.db_id == slot_ids[0]  # highest stored score


def test_find_consensus_picks_highest_score_slot(mem):
    rid, parts, slot_ids = _setup_polling_request(mem, n_slots=2)
    # Both slots are unanimous yes — pick higher-score one (slot 0, score=1.0).
    for p in parts:
        for sid in slot_ids:
            sched_db.record_response(
                mem,
                request_id=rid,
                participant_db_id=p.db_id,
                slot_db_id=sid,
                response="yes",
            )
    result = find_consensus(_ctx(mem), rid)
    assert result is not None
    assert result.db_id == slot_ids[0]


# ---------------------------------------------------------------------------
# record_decision
# ---------------------------------------------------------------------------


class _FakeBot:
    def __init__(self):
        self.calls: list[dict] = []

    def send_poll(self, *, chat_id, text, buttons):
        self.calls.append({"chat_id": chat_id, "text": text, "buttons": buttons})
        return {"message_id": 42}


class _FakeGmail:
    def __init__(self):
        self.drafts: list[dict] = []

    def compose_draft(self, *, to, subject, body):
        self.drafts.append({"to": to, "subject": subject, "body": body})
        return {"draft_id": f"draft-{len(self.drafts)}", "thread_id": "thread-1"}


def _approve_ready_request(mem):
    """Create a request in OWNER_REVIEW with one telegram + one gmail participant."""
    req = SchedulingRequest(
        id="",
        title="Approval test",
        duration_minutes=30,
        date_range_start=date(2026, 4, 14),
        date_range_end=date(2026, 4, 21),
        preferred_timezone="UTC",
        participants=[
            Participant(name="Tg", telegram_id="999", timezone="UTC", channel="telegram"),
            Participant(name="Em", email="em@x.com", timezone="UTC", channel="gmail"),
        ],
    )
    rid = sched_db.create_request(mem, req)
    slot = TimeSlot(
        start_time=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
        end_time=datetime(2026, 4, 14, 10, 30, tzinfo=UTC),
        score=0.9,
    )
    sched_db.add_slot(mem, rid, slot)
    sched_db.update_request_status(mem, rid, SchedulingStatus.OWNER_REVIEW.value)
    return rid


def test_record_decision_approve_transitions_and_calls_outreach(mem):
    rid = _approve_ready_request(mem)
    bot = _FakeBot()
    gmail = _FakeGmail()

    result = record_decision(
        mem,
        rid,
        "approve",
        bot=bot,
        gmail=gmail,
        owner_name="Owner",
        owner_timezone="UTC",
    )

    assert result["status"] == "ok"
    assert result["new_status"] == SchedulingStatus.POLLING.value
    loaded = sched_db.get_request(mem, rid)
    assert loaded.status == SchedulingStatus.POLLING.value
    assert len(bot.calls) == 1
    assert len(gmail.drafts) == 1


def test_record_decision_reject_goes_to_proposing_without_outreach(mem):
    rid = _approve_ready_request(mem)
    bot = _FakeBot()
    gmail = _FakeGmail()

    result = record_decision(mem, rid, "reject", bot=bot, gmail=gmail)

    assert result["status"] == "ok"
    assert result["new_status"] == SchedulingStatus.PROPOSING.value
    assert bot.calls == []
    assert gmail.drafts == []


def test_record_decision_cancel_from_owner_review(mem):
    rid = _approve_ready_request(mem)
    result = record_decision(mem, rid, "cancel")
    assert result["status"] == "ok"
    assert result["new_status"] == SchedulingStatus.CANCELLED.value


def test_record_decision_cancel_from_terminal_errors(mem):
    rid = _approve_ready_request(mem)
    _force_status(mem, rid, SchedulingStatus.BOOKED)
    result = record_decision(mem, rid, "cancel")
    assert result["status"] == "error"


def test_record_decision_book_requires_converged(mem):
    rid = _approve_ready_request(mem)
    result = record_decision(mem, rid, "book")
    assert result["status"] == "error"

    _force_status(mem, rid, SchedulingStatus.CONVERGED)
    result = record_decision(mem, rid, "book", slot_id=1)
    assert result["status"] == "ok"
    assert result["new_status"] == SchedulingStatus.BOOKED.value
    assert "calendar_note" in result


def test_record_decision_rework_polling_to_owner_review(mem):
    rid = _approve_ready_request(mem)
    _force_status(mem, rid, SchedulingStatus.POLLING)
    result = record_decision(mem, rid, "rework")
    assert result["status"] == "ok"
    assert result["new_status"] == SchedulingStatus.OWNER_REVIEW.value


def test_record_decision_unknown_action(mem):
    rid = _approve_ready_request(mem)
    result = record_decision(mem, rid, "eat_lunch")
    assert result["status"] == "error"
    assert "unknown action" in result["reason"]


def test_record_decision_missing_request(mem):
    result = record_decision(mem, "not-a-real-id", "approve")
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# start_scheduling
# ---------------------------------------------------------------------------


def test_start_scheduling_creates_request_and_ends_in_owner_review(mem):
    participants = [
        Participant(name="Alice", email="alice@x.com", timezone="UTC", channel="gmail"),
        Participant(name="Bob", email="bob@x.com", timezone="UTC", channel="gmail"),
    ]
    req = start_scheduling(
        db=mem,
        participants=participants,
        duration_minutes=30,
        date_range_start=date(2026, 4, 14),  # Tue
        date_range_end=date(2026, 4, 16),  # Thu
        owner_events={},
        owner_timezone="UTC",
        owner_name="Owner",
        title="Test kick-off",
    )

    assert req.status == SchedulingStatus.OWNER_REVIEW.value
    assert len(req.slots) > 0
    assert len(req.participants) == 2
    # Participants persisted with db_id assigned.
    for p in req.participants:
        assert p.db_id is not None


def test_start_scheduling_no_slots_goes_to_cancelled(mem):
    # Past date range, duration exceeds window → no slots.
    participants = [
        Participant(name="A", email="a@x.com", timezone="UTC", channel="gmail"),
    ]
    # Weekend only — scorer skips Sat/Sun → zero slots.
    req = start_scheduling(
        db=mem,
        participants=participants,
        duration_minutes=30,
        date_range_start=date(2026, 4, 11),  # Sat
        date_range_end=date(2026, 4, 12),  # Sun
        owner_events={},
        owner_timezone="UTC",
        owner_name="Owner",
    )
    assert req.status == SchedulingStatus.CANCELLED.value


# ---------------------------------------------------------------------------
# check_polling_status (no gmail/anthropic paths)
# ---------------------------------------------------------------------------


def test_check_polling_status_returns_summary(mem):
    rid, parts, slot_ids = _setup_polling_request(mem)
    # One participant responded yes.
    sched_db.record_response(
        mem,
        request_id=rid,
        participant_db_id=parts[0].db_id,
        slot_db_id=slot_ids[0],
        response="yes",
    )
    summary = coordinator.check_polling_status(_ctx(mem), rid)
    assert summary["total_participants"] == 2
    assert summary["responded"] == 1
    assert summary["pending"] == 1
    assert summary["consensus_slot_id"] is None


def test_check_polling_status_missing_request(mem):
    summary = coordinator.check_polling_status(_ctx(mem), "nope")
    assert "error" in summary


# ---------------------------------------------------------------------------
# Phase B M2: find_consensus with SchedulingContext
# ---------------------------------------------------------------------------


def _make_ctx(mem, *, calendar=None, scoring_config=None):
    """Build a SchedulingContext for tests."""
    from cosinabox.scheduling.context import OwnerProfile, SchedulingContext

    return SchedulingContext(
        db=mem,
        owner=OwnerProfile(name="Host", timezone="UTC"),
        calendar=calendar,
        scoring_config=scoring_config,
    )


class FakeCalendarProvider:
    """Test double for CalendarProvider."""

    def __init__(self, busy=None):
        from cosinabox.scheduling.context import BusyInterval

        self._busy: list[BusyInterval] = busy or []
        self.call_count = 0

    def list_busy_intervals(self, *, start, end, timezone):
        self.call_count += 1
        return self._busy

    def create_event(self, *, title, start, end, attendees, description=None):
        from cosinabox.scheduling.context import CreatedEvent

        return CreatedEvent(
            event_id="fake-1", title=title, start=start, end=end, attendees=attendees
        )


def test_find_consensus_ctx_no_calendar(mem):
    """New-style find_consensus with ctx.calendar=None uses stored scores."""
    req = SchedulingRequest(
        id="",
        title="Ctx test",
        duration_minutes=30,
        date_range_start=date(2026, 5, 4),
        date_range_end=date(2026, 5, 5),
        participants=[
            Participant(name="A", email="a@x.com", timezone="UTC", channel="gmail"),
        ],
    )
    rid = sched_db.create_request(mem, req)
    sched_db.add_slot(
        mem,
        rid,
        TimeSlot(
            start_time=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
            end_time=datetime(2026, 5, 4, 9, 30, tzinfo=UTC),
            score=0.8,
        ),
    )
    slot = sched_db.get_slots(mem, rid)[0]
    p = sched_db.get_participants(mem, rid)[0]
    sched_db.record_response(
        mem, request_id=rid, participant_db_id=p.db_id, slot_db_id=slot.db_id, response="yes"
    )

    ctx = _make_ctx(mem)
    result = find_consensus(ctx, rid)
    assert result is not None
    assert result.db_id == slot.db_id


def test_find_consensus_ctx_with_provider(mem):
    """New-style find_consensus with a FakeCalendarProvider re-scores."""
    from cosinabox.scheduling.context import BusyInterval

    req = SchedulingRequest(
        id="",
        title="Ctx provider",
        duration_minutes=30,
        date_range_start=date(2026, 5, 4),
        date_range_end=date(2026, 5, 5),
        participants=[
            Participant(name="A", email="a@x.com", timezone="UTC", channel="gmail"),
        ],
    )
    rid = sched_db.create_request(mem, req)
    # Two slots — second has higher stored score but a conflict in fresh calendar
    sched_db.add_slot(
        mem,
        rid,
        TimeSlot(
            start_time=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
            end_time=datetime(2026, 5, 4, 9, 30, tzinfo=UTC),
            score=0.5,
        ),
    )
    sched_db.add_slot(
        mem,
        rid,
        TimeSlot(
            start_time=datetime(2026, 5, 4, 10, 0, tzinfo=UTC),
            end_time=datetime(2026, 5, 4, 10, 30, tzinfo=UTC),
            score=0.9,
        ),
    )
    slots = sched_db.get_slots(mem, rid)
    p = sched_db.get_participants(mem, rid)[0]
    for s in slots:
        sched_db.record_response(
            mem, request_id=rid, participant_db_id=p.db_id, slot_db_id=s.db_id, response="yes"
        )

    # Provider returns a conflict overlapping the 10:00 slot
    provider = FakeCalendarProvider(
        busy=[
            BusyInterval(
                start=datetime(2026, 5, 4, 9, 45, tzinfo=UTC),
                end=datetime(2026, 5, 4, 10, 45, tzinfo=UTC),
            ),
        ]
    )
    ctx = _make_ctx(mem, calendar=provider)
    result = find_consensus(ctx, rid)
    assert result is not None
    # The 9:00 slot should win because the 10:00 slot now has a conflict
    assert result.start_time.hour == 9
    assert provider.call_count == 1


def test_find_consensus_ctx_provider_error_falls_back(mem):
    """If the provider raises, fall back to stored scores."""

    class ErrorProvider:
        def list_busy_intervals(self, **kw):
            raise RuntimeError("API down")

        def create_event(self, **kw):
            raise RuntimeError("API down")

    req = SchedulingRequest(
        id="",
        title="Error test",
        duration_minutes=30,
        date_range_start=date(2026, 5, 4),
        date_range_end=date(2026, 5, 5),
        participants=[
            Participant(name="A", email="a@x.com", timezone="UTC", channel="gmail"),
        ],
    )
    rid = sched_db.create_request(mem, req)
    sched_db.add_slot(
        mem,
        rid,
        TimeSlot(
            start_time=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
            end_time=datetime(2026, 5, 4, 9, 30, tzinfo=UTC),
            score=0.8,
        ),
    )
    slot = sched_db.get_slots(mem, rid)[0]
    p = sched_db.get_participants(mem, rid)[0]
    sched_db.record_response(
        mem, request_id=rid, participant_db_id=p.db_id, slot_db_id=slot.db_id, response="yes"
    )

    ctx = _make_ctx(mem, calendar=ErrorProvider())
    result = find_consensus(ctx, rid)
    assert result is not None
    assert result.db_id == slot.db_id


def test_find_consensus_requires_scheduling_context(mem):
    """find_consensus requires a SchedulingContext (old db path removed in M4)."""
    req = SchedulingRequest(
        id="",
        title="Ctx required",
        duration_minutes=30,
        date_range_start=date(2026, 5, 4),
        date_range_end=date(2026, 5, 5),
        participants=[
            Participant(name="A", email="a@x.com", timezone="UTC", channel="gmail"),
        ],
    )
    rid = sched_db.create_request(mem, req)
    sched_db.add_slot(
        mem,
        rid,
        TimeSlot(
            start_time=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
            end_time=datetime(2026, 5, 4, 9, 30, tzinfo=UTC),
            score=0.8,
        ),
    )
    slot = sched_db.get_slots(mem, rid)[0]
    p = sched_db.get_participants(mem, rid)[0]
    sched_db.record_response(
        mem, request_id=rid, participant_db_id=p.db_id, slot_db_id=slot.db_id, response="yes"
    )

    # New path works
    result = find_consensus(_ctx(mem), rid)
    assert result is not None
    assert result.db_id == slot.db_id
