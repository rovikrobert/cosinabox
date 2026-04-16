"""Tests for the Telegram scheduling-callback handler."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from cosinabox.bot.scheduling_callbacks import build_scheduling_callback_handler
from cosinabox.bot.telegram import TelegramBot
from cosinabox.memory import Memory
from cosinabox.scheduling import db as sched_db
from cosinabox.scheduling.models import (
    Participant,
    SchedulingRequest,
    SchedulingStatus,
    TimeSlot,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mem(tmp_path):
    return Memory(db_path=tmp_path / "test.db")


@pytest.fixture
def seeded(mem):
    """Insert a scheduling request + participant + two slots. Return ids."""
    req = SchedulingRequest(
        id=None,
        title="Sync",
        duration_minutes=30,
        participants=[
            Participant(
                name="Alice", email="a@x.com", telegram_id="111",
                timezone="UTC", channel="telegram",
            ),
        ],
        date_range_start=date.today(),
        date_range_end=date.today() + timedelta(days=7),
        status=SchedulingStatus.POLLING.value,
        preferred_timezone="UTC",
    )
    req_id = sched_db.create_request(mem, req)
    participant_id = req.participants[0].db_id

    start = datetime.now(UTC) + timedelta(days=1)
    slot1_id = sched_db.add_slot(
        mem, req_id, TimeSlot(start_time=start, end_time=start + timedelta(minutes=30)),
    )
    slot2_id = sched_db.add_slot(
        mem, req_id, TimeSlot(
            start_time=start + timedelta(hours=2),
            end_time=start + timedelta(hours=2, minutes=30),
        ),
    )
    return {
        "req_id": req_id,
        "participant_id": participant_id,
        "slot_ids": (slot1_id, slot2_id),
    }


def _make_update(data: str, from_user_id: int | str | None = None):
    """Build a fake Update with ``callback_query.data == data`` and an awaitable ``answer``."""
    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.data = data
    update.callback_query.answer = AsyncMock()
    update.callback_query.from_user = MagicMock()
    update.callback_query.from_user.id = from_user_id
    return update


@pytest.fixture
def seeded_with_telegram(mem):
    """Seed a request with a participant who has a known telegram_id."""
    req = SchedulingRequest(
        id=None,
        title="Sync",
        duration_minutes=30,
        participants=[
            Participant(
                name="Alice", email="a@x.com", telegram_id="111",
                timezone="UTC", channel="telegram",
            ),
        ],
        date_range_start=date.today(),
        date_range_end=date.today() + timedelta(days=7),
        status=SchedulingStatus.POLLING.value,
        preferred_timezone="UTC",
    )
    req_id = sched_db.create_request(mem, req)
    participant_id = req.participants[0].db_id
    start = datetime.now(UTC) + timedelta(days=1)
    slot_id = sched_db.add_slot(
        mem, req_id, TimeSlot(start_time=start, end_time=start + timedelta(minutes=30)),
    )
    return {"req_id": req_id, "participant_id": participant_id, "slot_id": slot_id}


# ---------------------------------------------------------------------------
# build_scheduling_callback_handler — behavior
# ---------------------------------------------------------------------------


async def test_valid_single_slot_records_response_and_answers(mem, seeded) -> None:
    handler = build_scheduling_callback_handler(mem)
    slot_id = seeded["slot_ids"][0]
    data = f"sched_resp:{seeded['req_id']}:{seeded['participant_id']}:{slot_id}"
    update = _make_update(data, from_user_id=111)

    await handler(update, MagicMock())

    update.callback_query.answer.assert_awaited_once()
    # Confirmation toast, not an alert
    args, kwargs = update.callback_query.answer.call_args
    assert "Thanks" in (args[0] if args else kwargs.get("text", ""))
    assert kwargs.get("show_alert") is False

    responses = sched_db.get_responses(mem, seeded["req_id"])
    assert len(responses) == 1
    assert responses[0]["slot_id"] == slot_id
    assert responses[0]["response"] == "yes"
    assert responses[0]["participant_id"] == seeded["participant_id"]


async def test_valid_multi_slot_records_one_per_slot(mem, seeded) -> None:
    handler = build_scheduling_callback_handler(mem)
    s1, s2 = seeded["slot_ids"]
    data = f"sched_resp:{seeded['req_id']}:{seeded['participant_id']}:{s1},{s2}"
    update = _make_update(data, from_user_id=111)

    await handler(update, MagicMock())

    responses = sched_db.get_responses(mem, seeded["req_id"])
    recorded_slots = sorted(r["slot_id"] for r in responses)
    assert recorded_slots == sorted([s1, s2])
    assert all(r["response"] == "yes" for r in responses)
    update.callback_query.answer.assert_awaited_once()


async def test_malformed_callback_shows_invalid_format_alert(mem) -> None:
    handler = build_scheduling_callback_handler(mem)
    update = _make_update("sched_resp:only-two-parts")

    await handler(update, MagicMock())

    update.callback_query.answer.assert_awaited_once_with(
        "Invalid response format", show_alert=True,
    )


async def test_empty_callback_data_shows_invalid_format_alert(mem) -> None:
    handler = build_scheduling_callback_handler(mem)
    update = _make_update("")

    await handler(update, MagicMock())

    update.callback_query.answer.assert_awaited_once_with(
        "Invalid response format", show_alert=True,
    )


async def test_db_error_shows_error_alert_and_no_confirmation(mem, seeded) -> None:
    # Use real db for the identity/slot checks, then force record_response to fail.
    handler = build_scheduling_callback_handler(mem)
    slot_id = seeded["slot_ids"][0]
    data = f"sched_resp:{seeded['req_id']}:{seeded['participant_id']}:{slot_id}"
    update = _make_update(data, from_user_id=111)

    import cosinabox.bot.scheduling_callbacks as cb
    original = cb.sched_db.record_response

    def _boom(*_a, **_kw):
        raise RuntimeError("db offline")

    cb.sched_db.record_response = _boom
    try:
        await handler(update, MagicMock())
    finally:
        cb.sched_db.record_response = original

    update.callback_query.answer.assert_awaited_once_with(
        "Error recording response", show_alert=True,
    )


# ---------------------------------------------------------------------------
# Security: CSRF / forwarded-message + cross-request slot
# ---------------------------------------------------------------------------


async def test_callback_rejects_mismatched_from_user(mem, seeded_with_telegram) -> None:
    """If a different Telegram user taps a forwarded keyboard, reject it."""
    handler = build_scheduling_callback_handler(mem)
    s = seeded_with_telegram
    data = f"sched_resp:{s['req_id']}:{s['participant_id']}:{s['slot_id']}"
    # Attacker's Telegram user id (999) != participant telegram_id (111)
    update = _make_update(data, from_user_id=999)

    await handler(update, MagicMock())

    # No response recorded
    responses = sched_db.get_responses(mem, s["req_id"])
    assert len(responses) == 0
    # Alert shown to attacker
    update.callback_query.answer.assert_awaited_once()
    _, kwargs = update.callback_query.answer.call_args
    assert kwargs.get("show_alert") is True


async def test_callback_accepts_matching_from_user(mem, seeded_with_telegram) -> None:
    handler = build_scheduling_callback_handler(mem)
    s = seeded_with_telegram
    data = f"sched_resp:{s['req_id']}:{s['participant_id']}:{s['slot_id']}"
    update = _make_update(data, from_user_id=111)  # matches participant.telegram_id

    await handler(update, MagicMock())

    responses = sched_db.get_responses(mem, s["req_id"])
    assert len(responses) == 1


async def test_callback_rejects_slot_from_different_request(mem, seeded_with_telegram) -> None:
    """Slot id referenced in callback must belong to the request_id in the callback."""
    s = seeded_with_telegram
    # Create a second request with its own slot
    req2 = SchedulingRequest(
        id=None,
        title="Other",
        duration_minutes=30,
        participants=[
            Participant(
                name="Bob", email="b@x.com", telegram_id="222",
                timezone="UTC", channel="telegram",
            ),
        ],
        date_range_start=date.today(),
        date_range_end=date.today() + timedelta(days=7),
        status=SchedulingStatus.POLLING.value,
        preferred_timezone="UTC",
    )
    req2_id = sched_db.create_request(mem, req2)
    start2 = datetime.now(UTC) + timedelta(days=2)
    slot_from_req2 = sched_db.add_slot(
        mem, req2_id, TimeSlot(start_time=start2, end_time=start2 + timedelta(minutes=30)),
    )

    handler = build_scheduling_callback_handler(mem)
    # Construct an attacker callback that points at req_A but uses slot from req_B
    data = f"sched_resp:{s['req_id']}:{s['participant_id']}:{slot_from_req2}"
    update = _make_update(data, from_user_id=111)

    await handler(update, MagicMock())

    # No response recorded under either request
    assert sched_db.get_responses(mem, s["req_id"]) == []
    assert sched_db.get_responses(mem, req2_id) == []
    update.callback_query.answer.assert_awaited_once()


# ---------------------------------------------------------------------------
# TelegramBot.register_callback_handler — dispatch
# ---------------------------------------------------------------------------


async def test_bot_register_callback_handler_appends() -> None:
    bot = TelegramBot(token="fake")
    fn = AsyncMock()
    bot.register_callback_handler("sched_resp:", fn)
    assert ("sched_resp:", fn) in bot._callback_handlers


async def test_bot_on_callback_dispatches_to_matching_prefix() -> None:
    bot = TelegramBot(token="fake")
    sched_fn = AsyncMock()
    other_fn = AsyncMock()
    bot.register_callback_handler("other:", other_fn)
    bot.register_callback_handler("sched_resp:", sched_fn)

    update = _make_update("sched_resp:abc:1:2")
    await bot._on_callback(update, MagicMock())

    sched_fn.assert_awaited_once()
    other_fn.assert_not_awaited()


async def test_bot_on_callback_ignores_when_no_prefix_matches() -> None:
    bot = TelegramBot(token="fake")
    fn = AsyncMock()
    bot.register_callback_handler("sched_resp:", fn)

    update = _make_update("unrelated:payload")
    await bot._on_callback(update, MagicMock())

    fn.assert_not_awaited()
