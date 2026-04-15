"""Tests for backchannel priority classification + move proposal engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cosinabox.scheduling.backchannel import (
    PriorityConfig,
    classify_priority,
    propose_moves,
)
from cosinabox.scheduling.models import TimeSlot


# A fixed "now" well in the past relative to the events we construct,
# so proximity guard never fires unintentionally.
NOW = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)


def _event(
    *,
    summary: str = "Meeting",
    start_offset_hours: float = 72,
    duration_minutes: int = 30,
    status: str = "confirmed",
    attendees: list[dict] | None = None,
) -> dict:
    start = NOW + timedelta(hours=start_offset_hours)
    end = start + timedelta(minutes=duration_minutes)
    return {
        "summary": summary,
        "status": status,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
        "attendees": attendees or [],
    }


class TestClassifyPriority:
    def test_immovable_keyword(self):
        config = PriorityConfig(immovable_keywords=["board meeting"])
        ev = _event(summary="Q2 Board Meeting")
        assert classify_priority(ev, config, now=NOW) == "immovable"

    def test_high_keyword(self):
        config = PriorityConfig(high_priority_keywords=["partner"])
        ev = _event(summary="Partner sync with Acme")
        assert classify_priority(ev, config, now=NOW) == "high"

    def test_low_keyword_default(self):
        # Default config has "focus block" in low_priority_keywords.
        ev = _event(summary="Focus Block — deep work")
        assert classify_priority(ev, PriorityConfig(), now=NOW) == "low"

    def test_medium_default_with_one_external(self):
        # No keyword match, 1 external attendee → medium.
        ev = _event(
            summary="Catchup",
            attendees=[{"email": "alice@example.com"}],
        )
        assert classify_priority(ev, PriorityConfig(), now=NOW) == "medium"

    def test_high_from_attendee_count(self):
        ev = _event(
            summary="Team chat",
            attendees=[
                {"email": "a@x.com"},
                {"email": "b@x.com"},
                {"email": "c@x.com"},
            ],
        )
        assert classify_priority(ev, PriorityConfig(), now=NOW) == "high"

    def test_vip_domain_immovable(self):
        config = PriorityConfig(vip_domains=[".gov"])
        ev = _event(
            summary="Intro call",
            attendees=[{"email": "minister@agency.gov"}],
        )
        assert classify_priority(ev, config, now=NOW) == "immovable"

    def test_self_attendee_ignored(self):
        # Self attendee shouldn't count as external or trigger VIP.
        config = PriorityConfig(vip_domains=[".gov"])
        ev = _event(
            summary="Solo block",
            attendees=[{"email": "owner@self.gov", "self": True}],
        )
        # No external attendees, no keyword → default medium.
        assert classify_priority(ev, config, now=NOW) == "medium"

    def test_empty_config_defaults_to_low_or_medium(self):
        # With fully empty keyword config (but default low list), no event
        # ever becomes "immovable" or "high" by title.
        config = PriorityConfig(
            immovable_keywords=[],
            high_priority_keywords=[],
            low_priority_keywords=[],
            vip_domains=[],
        )
        # No keywords, no attendees, confirmed → medium default.
        ev = _event(summary="Random title")
        assert classify_priority(ev, config, now=NOW) == "medium"
        # Tentative → low.
        ev2 = _event(summary="Random title", status="tentative")
        assert classify_priority(ev2, config, now=NOW) == "low"

    def test_proximity_guard_forces_immovable(self):
        # Event 2h from now — always immovable regardless of keywords.
        config = PriorityConfig(low_priority_keywords=["focus block"])
        ev = _event(summary="Focus Block", start_offset_hours=2)
        assert classify_priority(ev, config, now=NOW) == "immovable"

    def test_proximity_guard_does_not_trigger_beyond_window(self):
        # Event 48h away — guard does not fire; keyword wins.
        config = PriorityConfig(low_priority_keywords=["focus block"])
        ev = _event(summary="Focus Block", start_offset_hours=48)
        assert classify_priority(ev, config, now=NOW) == "low"

    def test_low_wins_over_high_when_both_match(self):
        # Title matches both "focus" (low) and "partner" (high) — low wins
        # because focus time is personal time the owner can reclaim.
        config = PriorityConfig(
            high_priority_keywords=["partner"],
            low_priority_keywords=["focus"],
        )
        ev = _event(summary="Focus time prep for partner call")
        assert classify_priority(ev, config, now=NOW) == "low"


class TestProposeMoves:
    def _slot(self, hours_from_now: float, duration_min: int = 30, score: float = 0.8) -> TimeSlot:
        start = NOW + timedelta(hours=hours_from_now)
        return TimeSlot(
            start_time=start,
            end_time=start + timedelta(minutes=duration_min),
            score=score,
        )

    def test_max_moves_enforced(self):
        # Build 5 slots all conflicting with 5 low-priority events.
        config = PriorityConfig(max_moves_per_request=2)
        slots = [self._slot(48 + i * 2, score=0.9 - i * 0.1) for i in range(5)]
        events = []
        for s in slots:
            events.append({
                "summary": "focus block",
                "status": "confirmed",
                "start": {"dateTime": s.start_time.isoformat()},
                "end": {"dateTime": s.end_time.isoformat()},
                "attendees": [],
            })
        proposals = propose_moves(
            candidate_slots=slots,
            owner_events=events,
            owner_timezone="UTC",
            config=config,
            now=NOW,
        )
        assert len(proposals) == 2

    def test_skips_immovable_and_high(self):
        config = PriorityConfig(
            immovable_keywords=["board"],
            high_priority_keywords=["partner"],
        )
        slot = self._slot(48)
        immovable_ev = {
            "summary": "Board call",
            "status": "confirmed",
            "start": {"dateTime": slot.start_time.isoformat()},
            "end": {"dateTime": slot.end_time.isoformat()},
            "attendees": [],
        }
        high_ev = {
            "summary": "Partner sync",
            "status": "confirmed",
            "start": {"dateTime": slot.start_time.isoformat()},
            "end": {"dateTime": slot.end_time.isoformat()},
            "attendees": [],
        }
        proposals = propose_moves(
            candidate_slots=[slot],
            owner_events=[immovable_ev, high_ev],
            owner_timezone="UTC",
            config=config,
            now=NOW,
        )
        assert proposals == []

    def test_proposes_move_for_low_priority_conflict(self):
        slot = self._slot(48)
        ev = {
            "summary": "focus block",
            "status": "confirmed",
            "start": {"dateTime": slot.start_time.isoformat()},
            "end": {"dateTime": slot.end_time.isoformat()},
            "attendees": [],
        }
        proposals = propose_moves(
            candidate_slots=[slot],
            owner_events=[ev],
            owner_timezone="UTC",
            config=PriorityConfig(),
            now=NOW,
        )
        assert len(proposals) == 1
        p = proposals[0]
        assert p["priority"] == "low"
        assert p["slot"] is slot
        assert p["conflict_event"] is ev
        assert p["score_if_moved"] > slot.score

    def test_no_overlap_no_proposal(self):
        slot = self._slot(48)
        # Event is far away from the slot.
        far = NOW + timedelta(hours=100)
        ev = {
            "summary": "focus block",
            "status": "confirmed",
            "start": {"dateTime": far.isoformat()},
            "end": {"dateTime": (far + timedelta(minutes=30)).isoformat()},
            "attendees": [],
        }
        proposals = propose_moves(
            candidate_slots=[slot],
            owner_events=[ev],
            owner_timezone="UTC",
            config=PriorityConfig(),
            now=NOW,
        )
        assert proposals == []
