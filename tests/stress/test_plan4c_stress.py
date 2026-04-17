"""Plan 4C stress-test suite — adversarial edges + end-to-end flows.

Covers the Task 12 checklist plus 9 adversarial scenarios. Each test
is self-contained and uses heavy mocking for external services.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from cosinabox.memory import Memory
from cosinabox.scheduling import db as sched_db
from cosinabox.scheduling.coordinator import (
    InvalidTransition,
    check_polling_status,
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
from cosinabox.scheduling.outreach import execute_outreach
from cosinabox.scheduling.response_parser import (
    parse_callback_data,
    parse_response,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def mem(tmp_path):
    return Memory(db_path=tmp_path / "stress.db")


def _participant(**kw):
    defaults = dict(
        name="Alice",
        email="alice@x.com",
        telegram_id=None,
        timezone="UTC",
        channel="gmail",
    )
    defaults.update(kw)
    return Participant(**defaults)


def _ctx(mem, **overrides):
    """Build a minimal SchedulingContext for tests."""
    from cosinabox.scheduling.context import OwnerProfile, SchedulingContext

    defaults = {"db": mem, "owner": OwnerProfile(name="Host", timezone="UTC")}
    defaults.update(overrides)
    return SchedulingContext(**defaults)


def _mock_anthropic_response(text: str, in_tok: int = 200, out_tok: int = 50):
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    usage = MagicMock()
    usage.input_tokens = in_tok
    usage.output_tokens = out_tok
    usage.cache_creation_input_tokens = 0
    usage.cache_read_input_tokens = 0
    response.usage = usage
    return response


# ---------------------------------------------------------------------------
# 1. First-run end-to-end
# ---------------------------------------------------------------------------


def test_first_run_end_to_end(mem):
    """Fresh DB → start_scheduling → approve → polling → consensus → book."""
    participants = [
        _participant(name="Bob", email="bob@x.com", channel="gmail", timezone="UTC"),
    ]

    # Start scheduling (next Monday..Friday)
    today = date.today()
    # Find next Monday
    days_ahead = (7 - today.weekday()) % 7 or 7
    start = today + timedelta(days=days_ahead)
    end = start + timedelta(days=4)

    req = start_scheduling(
        db=mem,
        participants=participants,
        duration_minutes=30,
        date_range_start=start,
        date_range_end=end,
        owner_events=None,
        owner_timezone="UTC",
        owner_name="Host",
        title="Kickoff",
    )
    assert req.status == SchedulingStatus.OWNER_REVIEW.value
    assert len(req.slots) > 0

    # Approve — outreach with gmail mock
    gmail = MagicMock()
    gmail.compose_draft.return_value = {"draft_id": "d1", "thread_id": "t1"}
    result = record_decision(
        mem,
        req.id,
        "approve",
        gmail=gmail,
        owner_name="Host",
        owner_timezone="UTC",
    )
    assert result["status"] == "ok"
    assert result["new_status"] == "polling"

    # Record all-yes responses directly
    participants_fresh = sched_db.get_participants(mem, req.id)
    slots = sched_db.get_slots(mem, req.id)
    for p in participants_fresh:
        sched_db.record_response(
            mem,
            request_id=req.id,
            participant_db_id=p.db_id,
            slot_db_id=slots[0].db_id,
            response="yes",
        )

    cs = find_consensus(_ctx(mem), req.id)
    assert cs is not None
    assert cs.db_id == slots[0].db_id

    # Transition polling → converged manually, then book
    transition(mem, req.id, SchedulingStatus.POLLING, SchedulingStatus.CONVERGED)
    result = record_decision(mem, req.id, "book", slot_id=slots[0].db_id)
    assert result["status"] == "ok"
    assert result["new_status"] == "booked"
    assert "calendar_note" in result


# ---------------------------------------------------------------------------
# 2. Missing integrations — gmail=None, bot=None, both None
# ---------------------------------------------------------------------------


def _build_mixed_request(mem):
    req = SchedulingRequest(
        id="",
        title="Mixed",
        duration_minutes=30,
        date_range_start=date(2026, 5, 4),
        date_range_end=date(2026, 5, 8),
        preferred_timezone="UTC",
        participants=[
            _participant(name="TG", telegram_id="123", channel="telegram"),
            _participant(name="GM", email="gm@x.com", channel="gmail"),
        ],
    )
    rid = sched_db.create_request(mem, req)
    # add a slot
    sched_db.add_slot(
        mem,
        rid,
        TimeSlot(
            start_time=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
            end_time=datetime(2026, 5, 4, 9, 30, tzinfo=UTC),
            score=0.8,
        ),
    )
    return sched_db.get_request(mem, rid)


def test_outreach_gmail_none_telegram_works(mem):
    req = _build_mixed_request(mem)
    bot = MagicMock()
    bot.send_poll.return_value = {"message_id": 42}
    summary = execute_outreach(
        request=req,
        slots=req.slots,
        bot=bot,
        gmail=None,
        owner_name="Host",
        owner_timezone="UTC",
        db=mem,
    )
    assert "Telegram sent" in summary
    assert "TG" in summary
    assert "no gmail configured" in summary.lower()


def test_outreach_bot_none_gmail_works(mem):
    req = _build_mixed_request(mem)
    gmail = MagicMock()
    gmail.compose_draft.return_value = {"draft_id": "d", "thread_id": "t"}
    summary = execute_outreach(
        request=req,
        slots=req.slots,
        bot=None,
        gmail=gmail,
        owner_name="Host",
        owner_timezone="UTC",
        db=mem,
    )
    assert "Gmail drafts" in summary
    assert "no bot configured" in summary.lower()


def test_outreach_both_none_returns_error(mem):
    req = _build_mixed_request(mem)
    summary = execute_outreach(
        request=req,
        slots=req.slots,
        bot=None,
        gmail=None,
        owner_name="Host",
        owner_timezone="UTC",
        db=mem,
    )
    assert "error" in summary.lower()


# ---------------------------------------------------------------------------
# 3. No calendar / empty owner_events
# ---------------------------------------------------------------------------


def test_no_calendar_still_finds_slots(mem):
    """owner_events=None still yields candidate slots (just no conflict filtering)."""
    req = start_scheduling(
        db=mem,
        participants=[_participant(name="X", timezone="UTC", channel="gmail")],
        duration_minutes=30,
        date_range_start=date(2026, 5, 4),  # Monday
        date_range_end=date(2026, 5, 8),  # Friday
        owner_events=None,
        owner_timezone="UTC",
        owner_name="Host",
    )
    assert len(req.slots) > 0
    # And all slots have requires_move=None since there was no calendar
    for s in req.slots:
        assert s.requires_move is None


# ---------------------------------------------------------------------------
# 4. State-machine illegal transitions
# ---------------------------------------------------------------------------


ILLEGAL_PAIRS = [
    (SchedulingStatus.PROPOSING, SchedulingStatus.BOOKED),
    (SchedulingStatus.POLLING, SchedulingStatus.BOOKED),
    (SchedulingStatus.BOOKED, SchedulingStatus.POLLING),
    (SchedulingStatus.CANCELLED, SchedulingStatus.PROPOSING),
    (SchedulingStatus.OWNER_REVIEW, SchedulingStatus.BOOKED),
]


@pytest.mark.parametrize("frm,to", ILLEGAL_PAIRS)
def test_illegal_transitions_raise(mem, frm, to):
    req = SchedulingRequest(
        id="",
        title="T",
        duration_minutes=30,
        date_range_start=date(2026, 5, 4),
        date_range_end=date(2026, 5, 8),
        participants=[_participant()],
    )
    rid = sched_db.create_request(mem, req)
    with pytest.raises(InvalidTransition) as exc:
        transition(mem, rid, frm, to)
    # Error message names both states
    assert frm.value in str(exc.value)
    assert to.value in str(exc.value)


# ---------------------------------------------------------------------------
# 5. Hard-block 1am-6am enforcement
# ---------------------------------------------------------------------------


def test_hard_block_1am_6am_enforced(mem):
    """Owner in UTC, participant in a timezone that makes UTC 9am = their 1-6am."""
    # UTC 01:00-06:00 → put participant where these hours ARE 01:00-06:00 local
    # Simplest: owner UTC, participant UTC (so owner peak 9-12 is safe for them).
    # Flip: participant in Pacific/Kiritimati (UTC+14) → UTC 11:00 = 01:00 next day.
    # So owner's 9-12 UTC window = 23:00-02:00 for participant. Some of that is hard-blocked.
    participant = _participant(
        name="Far",
        timezone="Pacific/Kiritimati",
        channel="gmail",
    )
    req = start_scheduling(
        db=mem,
        participants=[participant],
        duration_minutes=30,
        date_range_start=date(2026, 5, 4),
        date_range_end=date(2026, 5, 8),
        owner_events=None,
        owner_timezone="UTC",
        owner_name="Host",
    )
    from zoneinfo import ZoneInfo

    ktz = ZoneInfo("Pacific/Kiritimati")
    for slot in req.slots:
        local = slot.start_time.astimezone(ktz)
        assert not (1 <= local.hour < 6), (
            f"Slot {slot.start_time} maps to {local} which is in hard block"
        )


# ---------------------------------------------------------------------------
# 6. Cost tracker is populated after parse_response
# ---------------------------------------------------------------------------


def test_cost_tracker_populated_after_parse_response():
    tracker = MagicMock()
    client = MagicMock()
    client.messages.create.return_value = _mock_anthropic_response('{"responses": {"1": "yes"}}')
    slots = [
        TimeSlot(
            start_time=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
            end_time=datetime(2026, 5, 4, 9, 30, tzinfo=UTC),
            db_id=1,
        )
    ]
    result = parse_response(
        participant_name="Alice",
        slots=slots,
        reply_text="Yes, slot 1 works",
        anthropic_client=client,
        cost_tracker=tracker,
    )
    assert "responses" in result
    tracker.record.assert_called_once()
    usd = tracker.record.call_args[0][0]
    assert usd > 0


# ---------------------------------------------------------------------------
# 7. FK cascade on request delete — currently no CASCADE; FK raises
# ---------------------------------------------------------------------------


def test_fk_delete_request_blocks_when_children_exist(mem):
    """Deleting a parent request with child participants MUST raise an FK error
    because schema has no ON DELETE CASCADE. This test documents current
    behavior — if it changes we want to know.
    """
    req = SchedulingRequest(
        id="",
        title="T",
        duration_minutes=30,
        date_range_start=date(2026, 5, 4),
        date_range_end=date(2026, 5, 5),
        participants=[_participant()],
    )
    rid = sched_db.create_request(mem, req)
    with pytest.raises(sqlite3.IntegrityError):
        mem._conn.execute("DELETE FROM scheduling_requests WHERE id = ?", (rid,))
        mem._conn.commit()


# ---------------------------------------------------------------------------
# 8. Concurrent poll races — no dedup guard in coordinator
# ---------------------------------------------------------------------------


def test_concurrent_poll_double_records_response(mem):
    """Two polling runs see the same Gmail reply → still one row. Protected by
    both (a) in-flight `already_responded` guard and (b) DB-level UNIQUE
    constraint on (request_id, participant_id, slot_id).
    """
    req = SchedulingRequest(
        id="",
        title="T",
        duration_minutes=30,
        date_range_start=date(2026, 5, 4),
        date_range_end=date(2026, 5, 5),
        participants=[
            _participant(
                name="A",
                email="a@x.com",
                channel="gmail",
            ),
        ],
    )
    rid = sched_db.create_request(mem, req)
    p = sched_db.get_participants(mem, rid)[0]
    sched_db.add_slot(
        mem,
        rid,
        TimeSlot(
            start_time=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
            end_time=datetime(2026, 5, 4, 9, 30, tzinfo=UTC),
        ),
    )
    slot = sched_db.get_slots(mem, rid)[0]

    # Set thread id so polling will fetch
    sched_db.update_participant_status(
        mem,
        p.db_id,
        "sent",
        gmail_thread_id="thread-1",
        mark_outreach_sent=True,
    )
    sched_db.update_request_status(mem, rid, "polling")

    gmail = MagicMock()
    gmail.list_thread_messages.return_value = [{"body": "yes slot 1 works"}]
    client = MagicMock()
    client.messages.create.return_value = _mock_anthropic_response(
        f'{{"responses": {{"{slot.db_id}": "yes"}}}}'
    )

    # First poll
    check_polling_status(_ctx(mem, gmail=gmail, anthropic_client=client), rid)
    # In the same invocation the participant is in `already_responded` so
    # subsequent polls in the SAME call won't re-record. But if the DB is
    # observed mid-flight by a concurrent worker, it would. Simulate by
    # deleting the response row between polls = impossible. Instead,
    # simulate by clearing the in-memory `already_responded` guard — this
    # is what a separate worker would see.
    # Actual test: call check_polling_status twice in sequence. The 2nd
    # call re-reads `get_responses`, sees the participant responded, and
    # skips. So sequential calls ARE safe. The race exists only if two
    # workers execute concurrently between the `get_responses` read and
    # the `record_response` write.
    check_polling_status(_ctx(mem, gmail=gmail, anthropic_client=client), rid)
    responses = sched_db.get_responses(mem, rid)
    # Sequential polling IS dedup-safe (via already_responded check).
    # We document this behavior here.
    assert len(responses) == 1, f"Sequential polling is dedup-safe. Got {len(responses)} responses."


# ---------------------------------------------------------------------------
# 9. Callback prefix matching — sched_resp: vs sched_respond:
# ---------------------------------------------------------------------------


def test_callback_prefix_strict():
    # Exact match
    ok = parse_callback_data("sched_resp:abc123:5:42")
    assert "error" not in ok
    # Similar-prefix "sched_respond:" must NOT match
    bad = parse_callback_data("sched_respond:abc123:5:42")
    # sched_respond:abc123:5:42 splits into 4 parts → prefix check kicks in
    # parts[0] = "sched_respond" != "sched_resp"
    assert "error" in bad
    assert "prefix" in bad["error"].lower()
    # Any other prefix also fails
    other = parse_callback_data("sched_other:abc:1:1")
    assert "error" in other


def test_callback_malformed_forms():
    # Empty payload
    assert "error" in parse_callback_data("")
    # Not enough parts
    assert "error" in parse_callback_data("sched_resp:")
    assert "error" in parse_callback_data("sched_resp:a:b")
    # Too many parts (extra colon)
    assert "error" in parse_callback_data("sched_resp::")
    # Non-integer ids
    assert "error" in parse_callback_data("sched_resp:abc:xyz:1")
    assert "error" in parse_callback_data("sched_resp:abc:5:abc")
    # Empty slot list
    assert "error" in parse_callback_data("sched_resp:abc:5:")


# ---------------------------------------------------------------------------
# 10. App init with no scheduling config
# ---------------------------------------------------------------------------


def test_build_tool_registry_with_no_scheduling_ctx():
    """scheduling_ctx=None → registry still builds, no scheduling tools registered."""
    from cosinabox.tools.registry import build_tool_registry

    tool_defs, handlers = build_tool_registry(
        {},  # empty tool_instances
        timezone="UTC",
        scheduling_ctx=None,
    )
    names = {t["name"] for t in tool_defs}
    assert "schedule_group_meeting" not in names
    assert "scheduling_respond" not in names
    assert "scheduling_status" not in names


def test_cosinabox_app_import_does_not_crash():
    import cosinabox.app  # noqa: F401


# ---------------------------------------------------------------------------
# 12. DST transition handling
# ---------------------------------------------------------------------------


def test_dst_boundary_no_crash(mem):
    """Scheduling across the US spring-forward DST transition (2026-03-08)."""
    participant = _participant(
        name="PDT",
        timezone="America/Los_Angeles",
        channel="gmail",
    )
    # Range spans the DST transition
    req = start_scheduling(
        db=mem,
        participants=[participant],
        duration_minutes=30,
        date_range_start=date(2026, 3, 9),  # Monday after DST
        date_range_end=date(2026, 3, 13),
        owner_events=None,
        owner_timezone="UTC",
        owner_name="Host",
    )
    # Should produce slots without crashing and tz labels should work
    assert len(req.slots) > 0
    from zoneinfo import ZoneInfo

    from cosinabox.scheduling.outreach import _tz_label

    # Mimic the caller: pass a datetime already-in-participant-tz.
    tz = ZoneInfo("America/Los_Angeles")
    at_pdt = datetime(2026, 6, 15, 12, 0, tzinfo=UTC).astimezone(tz)
    assert _tz_label("America/Los_Angeles", at_pdt) == "PDT"
    at_pst = datetime(2026, 1, 15, 12, 0, tzinfo=UTC).astimezone(tz)
    assert _tz_label("America/Los_Angeles", at_pst) == "PST"


# ---------------------------------------------------------------------------
# 13. Empty candidate slots → auto-cancel
# ---------------------------------------------------------------------------


def test_empty_slots_auto_cancel(mem):
    """Date range is only weekends → no working days → auto-cancel."""
    req = start_scheduling(
        db=mem,
        participants=[_participant()],
        duration_minutes=30,
        date_range_start=date(2026, 5, 9),  # Saturday
        date_range_end=date(2026, 5, 10),  # Sunday
        owner_events=None,
        owner_timezone="UTC",
        owner_name="Host",
    )
    assert req.status == SchedulingStatus.CANCELLED.value
    assert req.slots == []


# ---------------------------------------------------------------------------
# 14. Malformed callback from Telegram (handler-level)
# ---------------------------------------------------------------------------


def test_handler_malformed_callback_shows_alert(mem):
    """handle_scheduling_callback hits answer(show_alert=True), does not crash."""
    import asyncio

    from cosinabox.bot.scheduling_callbacks import (
        build_scheduling_callback_handler,
    )

    handler = build_scheduling_callback_handler(mem)

    for bad in ("sched_resp:", "sched_resp:abc", "sched_resp::", ""):
        update = MagicMock()
        update.callback_query = MagicMock()
        update.callback_query.data = bad
        # answer is awaited
        called = {}

        async def _answer(msg, show_alert=False, _called=called):
            _called["msg"] = msg
            _called["alert"] = show_alert

        update.callback_query.answer = _answer

        asyncio.run(handler(update, None))
        assert called.get("alert") is True, f"{bad!r} did not trigger alert"


# ---------------------------------------------------------------------------
# 15. Duplicate responses — current behavior (appends a new row)
# ---------------------------------------------------------------------------


def test_duplicate_response_upserts(mem):
    """Participant clicks twice on the same slot — UNIQUE constraint +
    ON CONFLICT DO UPDATE collapses to a single row with the latest response.
    Prevents storage bloat and concurrent-poll double-recording."""
    req = SchedulingRequest(
        id="",
        title="T",
        duration_minutes=30,
        date_range_start=date(2026, 5, 4),
        date_range_end=date(2026, 5, 5),
        participants=[_participant()],
    )
    rid = sched_db.create_request(mem, req)
    p = sched_db.get_participants(mem, rid)[0]
    sched_db.add_slot(
        mem,
        rid,
        TimeSlot(
            start_time=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
            end_time=datetime(2026, 5, 4, 9, 30, tzinfo=UTC),
        ),
    )
    slot = sched_db.get_slots(mem, rid)[0]

    sched_db.record_response(
        mem,
        request_id=rid,
        participant_db_id=p.db_id,
        slot_db_id=slot.db_id,
        response="yes",
    )
    sched_db.record_response(
        mem,
        request_id=rid,
        participant_db_id=p.db_id,
        slot_db_id=slot.db_id,
        response="no",
    )
    responses = sched_db.get_responses(mem, rid)
    assert len(responses) == 1
    assert responses[0]["response"] == "no"


# ---------------------------------------------------------------------------
# 16. Phase B M2: CalendarProvider called exactly once per find_consensus
# ---------------------------------------------------------------------------


class _CountingProvider:
    """Minimal CalendarProvider that counts calls."""

    def __init__(self):
        self.list_calls = 0
        self.create_calls = 0

    def list_busy_intervals(self, *, start, end, timezone):
        self.list_calls += 1
        return []

    def create_event(self, *, title, start, end, attendees, description=None):
        self.create_calls += 1
        from cosinabox.scheduling.context import CreatedEvent

        return CreatedEvent(event_id="fake", title=title, start=start, end=end, attendees=attendees)


def test_find_consensus_calls_provider_once_per_cycle(mem):
    """CalendarProvider.list_busy_intervals is called at most once per
    find_consensus invocation (no duplicate fetch)."""
    from cosinabox.scheduling.context import OwnerProfile, SchedulingContext

    req = SchedulingRequest(
        id="",
        title="ProviderCount",
        duration_minutes=30,
        date_range_start=date(2026, 5, 4),
        date_range_end=date(2026, 5, 5),
        participants=[_participant(name="A", email="a@x.com", channel="gmail")],
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

    provider = _CountingProvider()
    ctx = SchedulingContext(
        db=mem,
        owner=OwnerProfile(name="Host", timezone="UTC"),
        calendar=provider,
    )
    result = find_consensus(ctx, rid)
    assert result is not None
    assert provider.list_calls == 1, (
        f"Expected exactly 1 list_busy_intervals call, got {provider.list_calls}"
    )
    # Call again — should be another single call (no caching).
    find_consensus(ctx, rid)
    assert provider.list_calls == 2


# ---------------------------------------------------------------------------
# 17. Phase B M5: book creates calendar event
# ---------------------------------------------------------------------------


def test_book_creates_calendar_event(mem):
    """record_decision('book') with a CalendarProvider creates an event and
    persists the booked_event_id."""
    from cosinabox.scheduling.context import CreatedEvent

    class _BookProvider:
        def __init__(self):
            self.created = []

        def list_busy_intervals(self, **kw):
            return []

        def create_event(self, *, title, start, end, attendees, description=None):
            self.created.append({"title": title, "attendees": attendees})
            return CreatedEvent(
                event_id="evt-42", title=title, start=start, end=end, attendees=attendees
            )

    req = SchedulingRequest(
        id="",
        title="Book test",
        duration_minutes=30,
        date_range_start=date(2026, 5, 4),
        date_range_end=date(2026, 5, 5),
        participants=[_participant(name="Bob", email="bob@x.com", channel="gmail")],
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
    from cosinabox.scheduling.coordinator import transition

    transition(mem, rid, "proposing", "owner_review")
    transition(mem, rid, "owner_review", "polling")
    transition(mem, rid, "polling", "converged")

    provider = _BookProvider()
    result = record_decision(mem, rid, "book", slot_id=slot.db_id, calendar=provider)
    assert result["status"] == "ok"
    assert result["booked_event_id"] == "evt-42"
    assert "Created calendar event" in result.get("calendar_note", "")
    assert len(provider.created) == 1
    assert "bob@x.com" in provider.created[0]["attendees"]

    # Verify persisted in DB
    loaded = sched_db.get_request(mem, rid)
    assert loaded.booked_event_id == "evt-42"


def test_book_fails_gracefully_when_calendar_missing(mem):
    """record_decision('book') without a CalendarProvider still transitions
    to BOOKED and returns a helpful note."""
    req = SchedulingRequest(
        id="",
        title="No cal",
        duration_minutes=30,
        date_range_start=date(2026, 5, 4),
        date_range_end=date(2026, 5, 5),
        participants=[_participant(name="C", email="c@x.com", channel="gmail")],
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
    from cosinabox.scheduling.coordinator import transition

    transition(mem, rid, "proposing", "owner_review")
    transition(mem, rid, "owner_review", "polling")
    transition(mem, rid, "polling", "converged")

    result = record_decision(mem, rid, "book")
    assert result["status"] == "ok"
    assert result["new_status"] == "booked"
    assert "manually" in result.get("calendar_note", "").lower()


# ---------------------------------------------------------------------------
# 18. Phase B M6: nudge timestamp + participant-channel routing
# ---------------------------------------------------------------------------


def test_nudge_records_nudged_at_timestamp(mem):
    """record_nudge sets both status='nudged' and nudged_at timestamp."""
    req = SchedulingRequest(
        id="",
        title="Nudge test",
        duration_minutes=30,
        date_range_start=date(2026, 5, 4),
        date_range_end=date(2026, 5, 5),
        participants=[_participant(name="D", email="d@x.com", channel="gmail")],
    )
    rid = sched_db.create_request(mem, req)
    p = sched_db.get_participants(mem, rid)[0]
    sched_db.update_participant_status(mem, p.db_id, "sent", mark_outreach_sent=True)

    # Record nudge
    sched_db.record_nudge(mem, p.db_id)

    # Verify
    row = mem._conn.execute(
        "SELECT status, nudged_at FROM scheduling_participants WHERE id = ?",
        (p.db_id,),
    ).fetchone()
    assert row["status"] == "nudged"
    assert row["nudged_at"] is not None


def test_nudge_direct_telegram_when_flag_enabled(mem):
    """With nudge_participants_directly=True, the poll job sends a Telegram
    DM to the participant and still notifies the owner."""
    from unittest.mock import MagicMock

    from cosinabox.jobs.scheduling_poll_check import SchedulingPollCheckJob
    from cosinabox.scheduling.context import OwnerProfile, SchedulingContext

    bot = MagicMock()
    ctx = SchedulingContext(
        db=mem,
        owner=OwnerProfile(name="Host", timezone="UTC"),
        bot=bot,
        nudge_participants_directly=True,
    )

    alice = _participant(name="Alice", telegram_id="tg_alice", channel="telegram")
    req = SchedulingRequest(
        id="",
        title="Direct nudge",
        duration_minutes=30,
        date_range_start=date(2026, 5, 4),
        date_range_end=date(2026, 5, 5),
        participants=[alice],
    )
    rid = sched_db.create_request(mem, req)
    p = sched_db.get_participants(mem, rid)[0]
    sched_db.update_participant_status(mem, p.db_id, "sent", mark_outreach_sent=True)
    sched_db.update_request_status(mem, rid, "polling")

    # Age the outreach to 25h
    from datetime import timedelta

    old_time = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    mem._conn.execute(
        "UPDATE scheduling_participants SET outreach_sent_at = ? WHERE id = ?",
        (old_time, p.db_id),
    )
    mem._conn.commit()

    send = []
    job = SchedulingPollCheckJob(ctx=ctx, send_fn=lambda t: send.append(t))
    job.run()

    # Bot should have been called to send a direct DM
    bot.send_message.assert_called_once()
    call_kwargs = bot.send_message.call_args
    assert call_kwargs[1]["chat_id"] == "tg_alice"

    # Owner also notified
    assert len(send) >= 1
    assert "direct nudge sent" in send[0].lower()
