"""Tests for scheduling outreach (Telegram + Gmail, sync)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock

from cosinabox.scheduling.models import (
    Participant,
    SchedulingRequest,
    TimeSlot,
)
from cosinabox.scheduling.outreach import (
    execute_outreach,
    send_gmail_draft,
    send_telegram_poll,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_slots(n: int = 3) -> list[TimeSlot]:
    base = datetime(2026, 5, 1, 9, 0, tzinfo=UTC)
    return [
        TimeSlot(
            start_time=base + timedelta(hours=i * 24),
            end_time=base + timedelta(hours=i * 24, minutes=30),
            score=1.0,
            db_id=100 + i,
        )
        for i in range(n)
    ]


def _make_request(participants: list[Participant]) -> SchedulingRequest:
    return SchedulingRequest(
        id="req_abc",
        title="Intro call",
        duration_minutes=30,
        participants=participants,
        date_range_start=date(2026, 5, 1),
        date_range_end=date(2026, 5, 7),
        preferred_timezone="Asia/Singapore",
    )


def _tg_participant(db_id: int = 11) -> Participant:
    return Participant(
        name="Alice Chen",
        email="alice@example.com",
        telegram_id="5551234",
        timezone="Asia/Singapore",
        channel="telegram",
        db_id=db_id,
    )


def _gm_participant(db_id: int = 22) -> Participant:
    return Participant(
        name="Bob Lee",
        email="bob@example.com",
        telegram_id=None,
        timezone="America/Los_Angeles",
        channel="gmail",
        db_id=db_id,
    )


# ---------------------------------------------------------------------------
# Telegram path
# ---------------------------------------------------------------------------


class TestSendTelegramPoll:
    def test_inline_keyboard_has_button_per_slot(self):
        bot = MagicMock()
        bot.send_poll.return_value = {"message_id": 42}
        participant = _tg_participant()
        slots = _make_slots(3)
        request = _make_request([participant])

        result = send_telegram_poll(
            bot=bot,
            participant=participant,
            request=request,
            slots=slots,
            owner_timezone="Asia/Singapore",
            owner_name="Rovik",
        )

        assert result["status"] == "sent"
        assert result["message_id"] == 42

        bot.send_poll.assert_called_once()
        kwargs = bot.send_poll.call_args.kwargs
        assert kwargs["chat_id"] == "5551234"
        buttons = kwargs["buttons"]
        assert len(buttons) == 3

    def test_callback_data_format(self):
        bot = MagicMock()
        bot.send_poll.return_value = {"message_id": 1}
        participant = _tg_participant(db_id=11)
        slots = _make_slots(2)
        request = _make_request([participant])

        send_telegram_poll(
            bot=bot,
            participant=participant,
            request=request,
            slots=slots,
            owner_timezone="Asia/Singapore",
            owner_name="Rovik",
        )

        buttons = bot.send_poll.call_args.kwargs["buttons"]
        # buttons are list of (label, callback_data)
        cbs = [cb for _, cb in buttons]
        assert cbs[0] == f"sched_resp:req_abc:11:{slots[0].db_id}"
        assert cbs[1] == f"sched_resp:req_abc:11:{slots[1].db_id}"

    def test_owner_name_in_message_text(self):
        bot = MagicMock()
        bot.send_poll.return_value = {"message_id": 1}
        participant = _tg_participant()
        slots = _make_slots(1)
        request = _make_request([participant])

        send_telegram_poll(
            bot=bot, participant=participant, request=request, slots=slots,
            owner_timezone="Asia/Singapore", owner_name="Keevs McTest",
        )
        text = bot.send_poll.call_args.kwargs["text"]
        assert "Keevs McTest" in text
        # No hardcoded "Rovik"
        assert "Rovik" not in text

    def test_no_telegram_id_returns_error(self):
        bot = MagicMock()
        participant = Participant(
            name="X", email="x@y.com", telegram_id=None,
            timezone="UTC", channel="telegram", db_id=1,
        )
        slots = _make_slots(1)
        request = _make_request([participant])

        result = send_telegram_poll(
            bot=bot, participant=participant, request=request, slots=slots,
            owner_timezone="UTC", owner_name="Owner",
        )
        assert result["status"] == "error"
        bot.send_poll.assert_not_called()

    def test_bot_exception_returns_error(self):
        bot = MagicMock()
        bot.send_poll.side_effect = RuntimeError("boom")
        participant = _tg_participant()
        slots = _make_slots(1)
        request = _make_request([participant])

        result = send_telegram_poll(
            bot=bot, participant=participant, request=request, slots=slots,
            owner_timezone="UTC", owner_name="Owner",
        )
        assert result["status"] == "error"
        assert "boom" in result["reason"]


# ---------------------------------------------------------------------------
# Gmail path
# ---------------------------------------------------------------------------


class TestSendGmailDraft:
    def test_draft_created_with_owner_and_timezone(self):
        gmail = MagicMock()
        gmail.compose_draft.return_value = {"draft_id": "d_789"}
        participant = _gm_participant()
        slots = _make_slots(2)
        request = _make_request([participant])

        result = send_gmail_draft(
            gmail=gmail,
            participant=participant,
            request=request,
            slots=slots,
            owner_name="Rovik Jeremiah",
            owner_timezone="Asia/Singapore",
        )

        assert result["status"] == "draft_created"
        assert result["draft_id"] == "d_789"

        kwargs = gmail.compose_draft.call_args.kwargs
        assert kwargs["to"] == "bob@example.com"
        assert "Intro call" in kwargs["subject"]

        body = kwargs["body"]
        assert "Rovik Jeremiah" in body
        # Body should show times localized to participant's timezone (LA => PDT/PST).
        # Accept either depending on DST; May is PDT.
        assert ("PDT" in body) or ("PST" in body) or ("Los_Angeles" in body)

    def test_no_email_returns_error(self):
        gmail = MagicMock()
        participant = Participant(
            name="X", email=None, telegram_id=None,
            timezone="UTC", channel="gmail", db_id=1,
        )
        slots = _make_slots(1)
        request = _make_request([participant])

        result = send_gmail_draft(
            gmail=gmail, participant=participant, request=request, slots=slots,
            owner_name="Owner", owner_timezone="UTC",
        )
        assert result["status"] == "error"
        gmail.compose_draft.assert_not_called()

    def test_gmail_exception_returns_error(self):
        gmail = MagicMock()
        gmail.compose_draft.side_effect = RuntimeError("api down")
        participant = _gm_participant()
        slots = _make_slots(1)
        request = _make_request([participant])

        result = send_gmail_draft(
            gmail=gmail, participant=participant, request=request, slots=slots,
            owner_name="Owner", owner_timezone="UTC",
        )
        assert result["status"] == "error"
        assert "api down" in result["reason"]


# ---------------------------------------------------------------------------
# execute_outreach orchestration
# ---------------------------------------------------------------------------


class TestExecuteOutreach:
    def test_dispatches_by_channel(self):
        bot = MagicMock()
        bot.send_poll.return_value = {"message_id": 1}
        gmail = MagicMock()
        gmail.compose_draft.return_value = {"draft_id": "d_1"}

        request = _make_request([_tg_participant(), _gm_participant()])
        slots = _make_slots(2)

        summary = execute_outreach(
            request=request, slots=slots, bot=bot, gmail=gmail,
            owner_name="Rovik", owner_timezone="Asia/Singapore",
        )
        assert "Alice Chen" in summary
        assert "Bob Lee" in summary
        assert "Telegram sent" in summary
        assert "Gmail drafts" in summary
        bot.send_poll.assert_called_once()
        gmail.compose_draft.assert_called_once()

    def test_missing_bot_skips_telegram_participants(self):
        gmail = MagicMock()
        gmail.compose_draft.return_value = {"draft_id": "d_1"}
        tg = _tg_participant()
        gm = _gm_participant()
        request = _make_request([tg, gm])
        slots = _make_slots(1)

        summary = execute_outreach(
            request=request, slots=slots, bot=None, gmail=gmail,
            owner_name="Owner", owner_timezone="UTC",
        )
        assert "Skipped" in summary
        assert "Alice Chen" in summary  # in skipped line
        assert "no bot configured" in summary
        # Gmail participant still handled
        assert "Gmail drafts" in summary

    def test_missing_gmail_skips_gmail_participants(self):
        bot = MagicMock()
        bot.send_poll.return_value = {"message_id": 1}
        tg = _tg_participant()
        gm = _gm_participant()
        request = _make_request([tg, gm])
        slots = _make_slots(1)

        summary = execute_outreach(
            request=request, slots=slots, bot=bot, gmail=None,
            owner_name="Owner", owner_timezone="UTC",
        )
        assert "Telegram sent" in summary
        assert "Skipped" in summary
        assert "Bob Lee" in summary
        assert "no gmail configured" in summary

    def test_all_no_channel_returns_error(self):
        tg = _tg_participant()
        gm = _gm_participant()
        request = _make_request([tg, gm])
        slots = _make_slots(1)

        summary = execute_outreach(
            request=request, slots=slots, bot=None, gmail=None,
            owner_name="Owner", owner_timezone="UTC",
        )
        assert "error" in summary.lower()

    def test_empty_participants_returns_error(self):
        request = _make_request([])
        slots = _make_slots(1)
        bot = MagicMock()
        gmail = MagicMock()

        summary = execute_outreach(
            request=request, slots=slots, bot=bot, gmail=gmail,
            owner_name="Owner", owner_timezone="UTC",
        )
        assert "error" in summary.lower()
