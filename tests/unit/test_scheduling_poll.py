"""Tests for SchedulingPollCheckJob — the 30-min polling worker."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from cosinabox.jobs.scheduling_poll_check import SchedulingPollCheckJob
from cosinabox.memory import Memory
from cosinabox.scheduling import db as sched_db
from cosinabox.scheduling.models import (
    Participant,
    SchedulingRequest,
    SchedulingStatus,
    TimeSlot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeSend:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, text: str) -> None:
        self.calls.append(text)


class _FakeAnthropic:
    """Sentinel — polling job never hits this directly in tests (gmail=None)."""


def _make_polling_request(
    mem: Memory,
    *,
    participants: list[Participant],
    n_slots: int = 2,
) -> str:
    req = SchedulingRequest(
        id="",
        title="Team sync",
        duration_minutes=30,
        date_range_start=date(2026, 4, 14),
        date_range_end=date(2026, 4, 21),
        preferred_timezone="UTC",
        participants=participants,
    )
    req_id = sched_db.create_request(mem, req)

    base = datetime(2026, 4, 15, 10, 0, tzinfo=UTC)
    for i in range(n_slots):
        slot = TimeSlot(
            start_time=base + timedelta(hours=i),
            end_time=base + timedelta(hours=i, minutes=30),
            score=1.0 - i * 0.1,
        )
        sched_db.add_slot(mem, req_id, slot)

    sched_db.update_request_status(mem, req_id, SchedulingStatus.POLLING.value)
    return req_id


def _set_outreach_sent_at(
    mem: Memory, participant_db_id: int, when: datetime, status: str = "sent",
) -> None:
    mem._conn.execute(
        "UPDATE scheduling_participants "
        "SET outreach_sent_at = ?, status = ? WHERE id = ?",
        (when.isoformat(), status, participant_db_id),
    )
    mem._conn.commit()


@pytest.fixture
def mem(tmp_path):
    return Memory(db_path=tmp_path / "poll.db")


@pytest.fixture
def job_factory(mem):
    def _make(send_fn=None):
        return SchedulingPollCheckJob(
            db=mem,
            anthropic_client=_FakeAnthropic(),
            gmail=None,
            cost_tracker=None,
            send_fn=send_fn or _FakeSend(),
        )
    return _make


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_active_polls_returns_skipped(mem, job_factory):
    job = job_factory()
    result = job.run()
    assert "skipped" in result


def test_consensus_transitions_to_converged(mem, job_factory):
    send = _FakeSend()
    alice = Participant(name="Alice", email="a@x.com", timezone="UTC", channel="gmail")
    bob = Participant(name="Bob", email="b@x.com", timezone="UTC", channel="gmail")
    req_id = _make_polling_request(mem, participants=[alice, bob], n_slots=2)

    hydrated = sched_db.get_request(mem, req_id)
    slot0 = hydrated.slots[0]
    p_alice, p_bob = hydrated.participants

    # Both say yes to slot 0.
    for p in (p_alice, p_bob):
        sched_db.record_response(
            mem,
            request_id=req_id,
            participant_db_id=p.db_id,
            slot_db_id=slot0.db_id,
            response="yes",
        )
        sched_db.update_participant_status(mem, p.db_id, "responded")

    job = job_factory(send_fn=send)
    result = job.run()

    after = sched_db.get_request(mem, req_id)
    assert after.status == SchedulingStatus.CONVERGED.value
    assert "1 converged" in result
    assert any("consensus" in msg.lower() for msg in send.calls)


def test_24h_old_no_response_triggers_nudge(mem, job_factory):
    send = _FakeSend()
    alice = Participant(name="Alice", email="a@x.com", timezone="UTC", channel="gmail")
    req_id = _make_polling_request(mem, participants=[alice])

    hydrated = sched_db.get_request(mem, req_id)
    p = hydrated.participants[0]

    # 25h old, status 'sent' (no response) → nudge
    _set_outreach_sent_at(
        mem, p.db_id, datetime.now(UTC) - timedelta(hours=25), status="sent",
    )

    job = job_factory(send_fn=send)
    result = job.run()

    refreshed = sched_db.get_participants(mem, req_id)[0]
    assert refreshed.status == "nudged"
    assert "1 nudged" in result
    assert any("nudge" in msg.lower() for msg in send.calls)

    # Request still POLLING (not converged, not expired).
    assert sched_db.get_request(mem, req_id).status == SchedulingStatus.POLLING.value


def test_48h_old_expires_and_all_expired_goes_to_owner_review(mem, job_factory):
    send = _FakeSend()
    alice = Participant(name="Alice", email="a@x.com", timezone="UTC", channel="gmail")
    req_id = _make_polling_request(mem, participants=[alice])

    hydrated = sched_db.get_request(mem, req_id)
    p = hydrated.participants[0]

    # 49h old → expires
    _set_outreach_sent_at(
        mem, p.db_id, datetime.now(UTC) - timedelta(hours=49), status="nudged",
    )

    job = job_factory(send_fn=send)
    result = job.run()

    refreshed = sched_db.get_participants(mem, req_id)[0]
    assert refreshed.status == "no_response"
    assert "1 expired" in result

    # All participants expired → owner review.
    assert (
        sched_db.get_request(mem, req_id).status
        == SchedulingStatus.OWNER_REVIEW.value
    )
    assert any("review" in msg.lower() for msg in send.calls)


def test_partial_expiry_stays_polling(mem, job_factory):
    """If some participants expire but others are still active, stay in POLLING."""
    send = _FakeSend()
    alice = Participant(name="Alice", email="a@x.com", timezone="UTC", channel="gmail")
    bob = Participant(name="Bob", email="b@x.com", timezone="UTC", channel="gmail")
    req_id = _make_polling_request(mem, participants=[alice, bob])

    hydrated = sched_db.get_request(mem, req_id)
    p_alice, p_bob = hydrated.participants

    # Alice: 49h old, already nudged → expire. Bob: 10h old → still active.
    _set_outreach_sent_at(
        mem, p_alice.db_id, datetime.now(UTC) - timedelta(hours=49), status="nudged",
    )
    _set_outreach_sent_at(
        mem, p_bob.db_id, datetime.now(UTC) - timedelta(hours=10), status="sent",
    )

    job = job_factory(send_fn=send)
    result = job.run()

    assert "1 expired" in result
    # Still POLLING — Bob not expired.
    assert sched_db.get_request(mem, req_id).status == SchedulingStatus.POLLING.value


def test_gmail_reply_parsed_and_recorded(mem, job_factory, monkeypatch):
    """When gmail returns a reply, check_polling_status parses and records it."""
    send = _FakeSend()
    alice = Participant(name="Alice", email="a@x.com", timezone="UTC", channel="gmail")
    req_id = _make_polling_request(mem, participants=[alice])

    hydrated = sched_db.get_request(mem, req_id)
    p = hydrated.participants[0]
    slot0 = hydrated.slots[0]

    # Attach a thread id so check_polling_status will fetch.
    mem._conn.execute(
        "UPDATE scheduling_participants SET gmail_thread_id = ? WHERE id = ?",
        ("thread-1", p.db_id),
    )
    mem._conn.commit()

    class _Gmail:
        def list_thread_messages(self, thread_id: str):
            assert thread_id == "thread-1"
            return [{"body": "ignored — parser is mocked"}]

    def _fake_parse_response(**kwargs):
        return {"responses": {str(slot0.db_id): "yes"}}

    # Patch the reference inside coordinator (imported at module scope).
    monkeypatch.setattr(
        "cosinabox.scheduling.coordinator.parse_response",
        _fake_parse_response,
    )

    job = SchedulingPollCheckJob(
        db=mem,
        anthropic_client=_FakeAnthropic(),
        gmail=_Gmail(),
        cost_tracker=None,
        send_fn=send,
    )
    result = job.run()

    responses = sched_db.get_responses(mem, req_id)
    assert len(responses) == 1
    assert responses[0]["response"] == "yes"
    assert responses[0]["slot_id"] == slot0.db_id

    # Single-participant unanimous yes → consensus → CONVERGED.
    assert sched_db.get_request(mem, req_id).status == SchedulingStatus.CONVERGED.value
    assert "1 converged" in result


def test_expire_age_without_prior_nudge_sends_nudge_first(mem, job_factory):
    """60h old, status still 'sent' (bot was down during 24-48h nudge window):
    send the nudge first; defer expire to next cycle."""
    send = _FakeSend()
    alice = Participant(name="Alice", email="a@x.com", timezone="UTC", channel="gmail")
    req_id = _make_polling_request(mem, participants=[alice])

    hydrated = sched_db.get_request(mem, req_id)
    p = hydrated.participants[0]

    _set_outreach_sent_at(
        mem, p.db_id, datetime.now(UTC) - timedelta(hours=60), status="sent",
    )

    job = job_factory(send_fn=send)
    result = job.run()

    refreshed = sched_db.get_participants(mem, req_id)[0]
    assert refreshed.status == "nudged"
    assert "1 nudged" in result
    assert "0 expired" in result
    assert any("nudge" in msg.lower() for msg in send.calls)
    # Request stays POLLING — not expired this cycle.
    assert sched_db.get_request(mem, req_id).status == SchedulingStatus.POLLING.value


def test_expire_age_with_prior_nudge_expires(mem, job_factory):
    send = _FakeSend()
    alice = Participant(name="Alice", email="a@x.com", timezone="UTC", channel="gmail")
    req_id = _make_polling_request(mem, participants=[alice])

    hydrated = sched_db.get_request(mem, req_id)
    p = hydrated.participants[0]

    _set_outreach_sent_at(
        mem, p.db_id, datetime.now(UTC) - timedelta(hours=60), status="nudged",
    )

    job = job_factory(send_fn=send)
    result = job.run()

    refreshed = sched_db.get_participants(mem, req_id)[0]
    assert refreshed.status == "no_response"
    assert "1 expired" in result


def test_expire_past_safety_cap_without_nudge(mem, job_factory):
    """80h old (past 72h safety cap), status='sent' — too old to nudge now, expire."""
    send = _FakeSend()
    alice = Participant(name="Alice", email="a@x.com", timezone="UTC", channel="gmail")
    req_id = _make_polling_request(mem, participants=[alice])

    hydrated = sched_db.get_request(mem, req_id)
    p = hydrated.participants[0]

    _set_outreach_sent_at(
        mem, p.db_id, datetime.now(UTC) - timedelta(hours=80), status="sent",
    )

    job = job_factory(send_fn=send)
    result = job.run()

    refreshed = sched_db.get_participants(mem, req_id)[0]
    assert refreshed.status == "no_response"
    assert "1 expired" in result


def test_no_outreach_sent_at_is_not_nudged(mem, job_factory):
    """A participant without outreach_sent_at (draft-only) should not be nudged/expired."""
    send = _FakeSend()
    alice = Participant(name="Alice", email="a@x.com", timezone="UTC", channel="gmail")
    req_id = _make_polling_request(mem, participants=[alice])

    # Leave status='pending', outreach_sent_at NULL.
    job = job_factory(send_fn=send)
    result = job.run()

    assert "0 nudged" in result
    assert "0 expired" in result
    assert sched_db.get_request(mem, req_id).status == SchedulingStatus.POLLING.value
