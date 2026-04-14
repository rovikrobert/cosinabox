"""Tests for slot scorer — hard block, overlap, scoring, candidate finder."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from cosinabox.scheduling.models import Participant
from cosinabox.scheduling.slot_scorer import (
    ScoringConfig,
    _any_participant_blocked,
    _is_in_hard_block,
    compute_overlap_window,
    compute_score,
    find_candidate_slots,
)


class TestHardBlock:
    def test_owner_asleep_at_3am(self):
        p = Participant(name="Owner", timezone="UTC")
        dt = datetime(2026, 4, 14, 3, 0, tzinfo=UTC)
        assert _is_in_hard_block(dt, p, ScoringConfig()) is True

    def test_owner_awake_at_10am(self):
        p = Participant(name="Owner", timezone="UTC")
        dt = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
        assert _is_in_hard_block(dt, p, ScoringConfig()) is False

    def test_asleep_in_different_timezone(self):
        # 2am SGT = 6pm UTC (day before). Owner in SGT is asleep.
        p = Participant(name="Owner", timezone="Asia/Singapore")
        dt_utc = datetime(2026, 4, 13, 18, 0, tzinfo=UTC)  # 2am SGT on Apr 14
        assert _is_in_hard_block(dt_utc, p, ScoringConfig()) is True

    def test_any_participant_blocked_returns_true(self):
        participants = [
            Participant(name="A", timezone="UTC"),
            Participant(name="B", timezone="Asia/Singapore"),
        ]
        # 6pm UTC = 2am SGT — B is asleep
        start = datetime(2026, 4, 13, 18, 0, tzinfo=UTC)
        end = start + timedelta(minutes=30)
        assert _any_participant_blocked(start, end, participants, ScoringConfig()) is True


class TestOverlapWindow:
    def test_empty_participants_full_day(self):
        result = compute_overlap_window([], date(2026, 4, 14), 30)
        assert result.available_minutes == 24 * 60
        assert result.message is None

    def test_single_participant_excludes_hard_block(self):
        p = Participant(name="A", timezone="UTC")
        result = compute_overlap_window([p], date(2026, 4, 14), 30)
        # 1-6am UTC excluded = 5 hours = 300 min. Available = 24*60 - 300 = 1140
        assert result.available_minutes == 1140

    def test_extreme_timezone_spread(self):
        # Tokyo (UTC+9) and San Francisco (UTC-8): very little overlap
        participants = [
            Participant(name="A", timezone="Asia/Tokyo"),
            Participant(name="B", timezone="America/Los_Angeles"),
        ]
        result = compute_overlap_window(participants, date(2026, 4, 14), 60)
        # Should have a narrow window or produce a warning
        assert result.available_minutes < 24 * 60

    def test_no_overlap_message(self):
        # Force impossible overlap by requiring longer than available
        participants = [Participant(name="A", timezone="UTC")]
        result = compute_overlap_window(participants, date(2026, 4, 14), 60 * 25)
        assert result.window_start_utc is None


class TestScoring:
    def test_owner_preference_peak(self):
        # 10am UTC (owner tz) = peak
        start = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
        end = start + timedelta(minutes=30)
        score = compute_score(
            start, end, [],
            busy=[], events_per_day={},
            range_start=date(2026, 4, 14), range_end=date(2026, 4, 14),
            owner_tz="UTC",
        )
        # Should score high (peak owner pref, no participants → fairness 1.0)
        assert score > 0.7

    def test_owner_preference_lunch(self):
        # 12:30pm UTC = avoid_hours
        start = datetime(2026, 4, 14, 12, 30, tzinfo=UTC)
        end = start + timedelta(minutes=30)
        score = compute_score(
            start, end, [],
            busy=[], events_per_day={},
            range_start=date(2026, 4, 14), range_end=date(2026, 4, 14),
            owner_tz="UTC",
        )
        # Lunch hour gets low owner preference — overall score dips
        peak_score = compute_score(
            datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
            datetime(2026, 4, 14, 10, 30, tzinfo=UTC), [],
            busy=[], events_per_day={},
            range_start=date(2026, 4, 14), range_end=date(2026, 4, 14),
            owner_tz="UTC",
        )
        assert score < peak_score

    def test_move_cost_penalty(self):
        start = datetime(2026, 4, 14, 10, 0, tzinfo=UTC)
        end = start + timedelta(minutes=30)
        no_move = compute_score(
            start, end, [], busy=[], events_per_day={},
            range_start=date(2026, 4, 14), range_end=date(2026, 4, 14),
            owner_tz="UTC",
        )
        needs_move = compute_score(
            start, end, [], busy=[], events_per_day={},
            range_start=date(2026, 4, 14), range_end=date(2026, 4, 14),
            owner_tz="UTC",
            requires_move="conflict:something",
        )
        assert no_move > needs_move


class TestFindCandidateSlots:
    def test_basic_candidate_generation(self):
        slots = find_candidate_slots(
            participants=[Participant(name="Alice", timezone="UTC")],
            date_range_start=date(2026, 4, 14),
            date_range_end=date(2026, 4, 14),
            duration_minutes=30,
            owner_events_by_day={},
            owner_timezone="UTC",
        )
        # Should return some slots (date is a Tuesday, not weekend)
        assert len(slots) > 0
        assert all(s.score > 0 for s in slots)

    def test_skips_weekends(self):
        # Saturday April 18, 2026
        slots = find_candidate_slots(
            participants=[Participant(name="Alice", timezone="UTC")],
            date_range_start=date(2026, 4, 18),
            date_range_end=date(2026, 4, 19),  # Sat + Sun
            duration_minutes=30,
            owner_events_by_day={},
            owner_timezone="UTC",
        )
        assert len(slots) == 0

    def test_top_n_limits(self):
        slots = find_candidate_slots(
            participants=[Participant(name="Alice", timezone="UTC")],
            date_range_start=date(2026, 4, 14),
            date_range_end=date(2026, 4, 16),
            duration_minutes=30,
            owner_events_by_day={},
            owner_timezone="UTC",
            top_n=3,
        )
        assert len(slots) <= 3

    def test_slots_sorted_by_score(self):
        slots = find_candidate_slots(
            participants=[Participant(name="Alice", timezone="UTC")],
            date_range_start=date(2026, 4, 14),
            date_range_end=date(2026, 4, 14),
            duration_minutes=30,
            owner_events_by_day={},
            owner_timezone="UTC",
        )
        for i in range(len(slots) - 1):
            assert slots[i].score >= slots[i + 1].score

    def test_respects_hard_block(self):
        slots = find_candidate_slots(
            participants=[Participant(name="Alice", timezone="UTC")],
            date_range_start=date(2026, 4, 14),
            date_range_end=date(2026, 4, 14),
            duration_minutes=30,
            owner_events_by_day={},
            owner_timezone="UTC",
        )
        # No slot should start at 3am UTC
        for slot in slots:
            local_hour = slot.start_time.astimezone(ZoneInfo("UTC")).hour
            assert not (1 <= local_hour < 6), (
                f"Slot at {slot.start_time} falls in hard block"
            )


class TestScoringConfig:
    def test_default_weights_sum_to_one(self):
        c = ScoringConfig()
        total = (
            c.w_timezone_fairness + c.w_owner_preference + c.w_buffer
            + c.w_move_cost + c.w_day_balance + c.w_recency
        )
        assert abs(total - 1.0) < 0.001

    def test_custom_config(self):
        config = ScoringConfig(
            peak_hours=(10, 14),
            hard_block_hours=(0, 7),
        )
        # 2am-7am UTC blocked for owner
        p = Participant(name="Owner", timezone="UTC")
        dt = datetime(2026, 4, 14, 6, 0, tzinfo=UTC)
        assert _is_in_hard_block(dt, p, config) is True
