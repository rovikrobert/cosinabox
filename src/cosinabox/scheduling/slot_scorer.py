"""Multi-timezone slot scoring engine.

Ported from cos-agent/src/scheduling/slot_scorer.py, converted to sync.
Owner's calendar events are passed in by the coordinator — this module
is pure algorithm, no I/O. Preferences are configurable via ScoringConfig.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from cosinabox.scheduling.models import Participant, TimeSlot

logger = logging.getLogger(__name__)


@dataclass
class ScoringConfig:
    """Configurable scoring parameters — replaces cos-agent's hardcoded constants."""

    peak_hours: tuple[int, int] = (9, 12)      # 9am-12pm in owner tz scores 1.0
    avoid_hours: tuple[int, int] = (12, 13)    # lunch — scores 0.2
    workday_hours: tuple[int, int] = (9, 18)   # outside this gets penalty

    hard_block_hours: tuple[int, int] = (1, 6)  # 1am-6am local NEVER propose
    work_hours_fairness: tuple[int, int] = (8, 19)  # fairness score: 8am-7pm = 1.0

    # Weights (must sum to 1.0)
    w_timezone_fairness: float = 0.30
    w_owner_preference: float = 0.25
    w_buffer: float = 0.15
    w_move_cost: float = 0.15
    w_day_balance: float = 0.10
    w_recency: float = 0.05

    slot_step_minutes: int = 30
    top_n: int = 5


@dataclass
class OverlapResult:
    window_start_utc: datetime | None
    window_end_utc: datetime | None
    available_minutes: int
    message: str | None = None


# ---------------------------------------------------------------------------
# Hard-block and overlap computation
# ---------------------------------------------------------------------------

def _is_in_hard_block(
    dt_utc: datetime, participant: Participant, config: ScoringConfig,
) -> bool:
    local = dt_utc.astimezone(ZoneInfo(participant.timezone))
    hb_start, hb_end = config.hard_block_hours
    return hb_start <= local.hour < hb_end


def _any_participant_blocked(
    start_utc: datetime, end_utc: datetime,
    participants: list[Participant], config: ScoringConfig,
) -> bool:
    cursor = start_utc
    while cursor < end_utc:
        for p in participants:
            if _is_in_hard_block(cursor, p, config):
                return True
        cursor += timedelta(minutes=15)
    return False


def _participant_utc_exclusion(
    participant: Participant, day: date, config: ScoringConfig,
) -> tuple[datetime, datetime]:
    """UTC exclusion range for a participant's hard block on a given day."""
    tz = ZoneInfo(participant.timezone)
    hb_start, hb_end = config.hard_block_hours
    local_block_start = datetime(day.year, day.month, day.day, hb_start, 0, tzinfo=tz)
    local_block_end = datetime(day.year, day.month, day.day, hb_end, 0, tzinfo=tz)
    utc = ZoneInfo("UTC")
    return local_block_start.astimezone(utc), local_block_end.astimezone(utc)


def compute_overlap_window(
    participants: list[Participant],
    day: date,
    duration_minutes: int,
    config: ScoringConfig | None = None,
) -> OverlapResult:
    """UTC window where all participants are outside their hard block."""
    config = config or ScoringConfig()
    utc = ZoneInfo("UTC")

    day_start = datetime(day.year, day.month, day.day, 0, 0, tzinfo=utc)
    day_end = day_start + timedelta(hours=24)

    if not participants:
        return OverlapResult(
            window_start_utc=day_start,
            window_end_utc=day_end,
            available_minutes=24 * 60,
        )

    # Collect UTC exclusion ranges (check prev/current/next day for DST boundaries).
    exclusion_ranges: list[tuple[datetime, datetime]] = []
    for p in participants:
        for offset_days in (-1, 0, 1):
            check_day = day + timedelta(days=offset_days)
            exc_start, exc_end = _participant_utc_exclusion(p, check_day, config)
            if exc_start < day_end and exc_end > day_start:
                exclusion_ranges.append((
                    max(exc_start, day_start),
                    min(exc_end, day_end),
                ))

    exclusion_ranges.sort()
    merged: list[tuple[datetime, datetime]] = []
    for s, e in exclusion_ranges:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    # Available windows = gaps between exclusions.
    available: list[tuple[datetime, datetime]] = []
    cursor = day_start
    for exc_start, exc_end in merged:
        if cursor < exc_start:
            available.append((cursor, exc_start))
        cursor = max(cursor, exc_end)
    if cursor < day_end:
        available.append((cursor, day_end))

    total_minutes = sum(
        int((w_end - w_start).total_seconds() / 60)
        for w_start, w_end in available
    )

    if total_minutes < duration_minutes or not available:
        cities = [p.timezone.split("/")[-1].replace("_", " ") for p in participants]
        return OverlapResult(
            window_start_utc=None,
            window_end_utc=None,
            available_minutes=total_minutes,
            message=(
                f"{' and '.join(cities)} only have {total_minutes} min of overlap "
                f"after excluding sleep hours. No slots for a {duration_minutes} min meeting."
            ),
        )

    best = max(available, key=lambda w: (w[1] - w[0]).total_seconds())
    best_minutes = int((best[1] - best[0]).total_seconds() / 60)

    message = None
    possible_slots = best_minutes // config.slot_step_minutes
    if possible_slots < 2:
        cities = [p.timezone.split("/")[-1].replace("_", " ") for p in participants]
        message = (
            f"Only a {best_minutes}-minute window works for all timezones "
            f"({', '.join(cities)}). Consider splitting into two meetings."
        )

    return OverlapResult(
        window_start_utc=best[0], window_end_utc=best[1],
        available_minutes=total_minutes, message=message,
    )


# ---------------------------------------------------------------------------
# Candidate slot generation
# ---------------------------------------------------------------------------

def _generate_raw_slots(
    day: date, duration_minutes: int,
    participants: list[Participant], config: ScoringConfig,
) -> list[tuple[datetime, datetime]]:
    duration = timedelta(minutes=duration_minutes)
    slots: list[tuple[datetime, datetime]] = []

    overlap = compute_overlap_window(participants, day, duration_minutes, config)
    if overlap.window_start_utc is None or overlap.available_minutes < duration_minutes:
        return slots

    cursor = overlap.window_start_utc
    window_end = overlap.window_end_utc

    while cursor + duration <= window_end:
        end = cursor + duration
        if not _any_participant_blocked(cursor, end, participants, config):
            slots.append((cursor, end))
        cursor += timedelta(minutes=config.slot_step_minutes)

    return slots


# ---------------------------------------------------------------------------
# Scoring dimensions
# ---------------------------------------------------------------------------

def _score_timezone_fairness(
    start_utc: datetime, end_utc: datetime,
    participants: list[Participant], config: ScoringConfig,
) -> float:
    if not participants:
        return 1.0

    work_start, work_end = config.work_hours_fairness
    scores: list[float] = []
    for p in participants:
        tz = ZoneInfo(p.timezone)
        local_start = start_utc.astimezone(tz)
        local_end = end_utc.astimezone(tz)
        mid_hour = (local_start.hour + local_end.hour) / 2.0

        if work_start <= mid_hour <= work_end:
            scores.append(1.0)
        elif 6 <= mid_hour < work_start:
            scores.append(0.5)
        elif work_end < mid_hour <= 22:
            scores.append(0.4)
        else:
            scores.append(0.1)

    return sum(scores) / len(scores)


def _score_owner_preference(
    start_utc: datetime, owner_tz: str, config: ScoringConfig,
) -> float:
    local_start = start_utc.astimezone(ZoneInfo(owner_tz))
    hour = local_start.hour
    peak_start, peak_end = config.peak_hours
    avoid_start, avoid_end = config.avoid_hours
    work_start, work_end = config.workday_hours

    if peak_start <= hour < peak_end:
        return 1.0
    if avoid_start <= hour < avoid_end:
        return 0.2
    if avoid_end <= hour < work_end:
        return 0.7
    if work_start - 1 <= hour < peak_start:
        return 0.6
    if work_end <= hour < 20:
        return 0.4
    return 0.1


def _score_buffer(
    start_utc: datetime, end_utc: datetime,
    busy: list[tuple[datetime, datetime]],
) -> float:
    min_buffer = timedelta(minutes=30)
    before_ok = True
    after_ok = True
    for bs, be in busy:
        if be <= start_utc and start_utc - be < min_buffer:
            before_ok = False
        if bs >= end_utc and bs - end_utc < min_buffer:
            after_ok = False
    if before_ok and after_ok:
        return 1.0
    if before_ok or after_ok:
        return 0.5
    return 0.2


def _score_day_balance(day: date, events_per_day: dict[date, int]) -> float:
    count = events_per_day.get(day, 0)
    if count == 0:
        return 1.0
    if count <= 2:
        return 0.8
    if count <= 4:
        return 0.5
    return 0.2


def _score_move_cost(requires_move: str | None) -> float:
    return 1.0 if requires_move is None else 0.5


def _score_recency(day: date, range_start: date, range_end: date) -> float:
    total_days = max((range_end - range_start).days, 1)
    day_offset = (day - range_start).days
    return max(0.0, 1.0 - (day_offset / total_days) * 0.5)


def compute_score(
    start_utc: datetime, end_utc: datetime,
    participants: list[Participant],
    busy: list[tuple[datetime, datetime]],
    events_per_day: dict[date, int],
    range_start: date, range_end: date,
    owner_tz: str,
    requires_move: str | None = None,
    config: ScoringConfig | None = None,
) -> float:
    config = config or ScoringConfig()
    day = start_utc.astimezone(ZoneInfo(owner_tz)).date()
    return (
        config.w_timezone_fairness * _score_timezone_fairness(start_utc, end_utc, participants, config)
        + config.w_owner_preference * _score_owner_preference(start_utc, owner_tz, config)
        + config.w_buffer * _score_buffer(start_utc, end_utc, busy)
        + config.w_day_balance * _score_day_balance(day, events_per_day)
        + config.w_move_cost * _score_move_cost(requires_move)
        + config.w_recency * _score_recency(day, range_start, range_end)
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_conflict(
    start_utc: datetime, end_utc: datetime,
    busy: list[tuple[datetime, datetime]],
) -> str | None:
    for bs, be in busy:
        if start_utc < be and end_utc > bs:
            return f"conflict:{bs.isoformat()}"
    return None


def _deduplicate_overlapping(slots: list[TimeSlot]) -> list[TimeSlot]:
    selected: list[TimeSlot] = []
    for slot in slots:
        overlaps = False
        for existing in selected:
            if (slot.start_time < existing.end_time
                    and slot.end_time > existing.start_time):
                overlaps = True
                break
        if not overlaps:
            selected.append(slot)
    return selected


def events_to_busy_intervals(
    events: list[dict[str, Any]], tz_name: str,
) -> list[tuple[datetime, datetime]]:
    """Convert Google Calendar event dicts to sorted, merged busy intervals."""
    tz = ZoneInfo(tz_name)
    busy: list[tuple[datetime, datetime]] = []
    for ev in events:
        start_str = ev.get("start", {}).get("dateTime") if isinstance(ev.get("start"), dict) else None
        end_str = ev.get("end", {}).get("dateTime") if isinstance(ev.get("end"), dict) else None
        if start_str and end_str:
            s = datetime.fromisoformat(start_str).astimezone(tz)
            e = datetime.fromisoformat(end_str).astimezone(tz)
            if s < e:
                busy.append((s, e))
    busy.sort()
    merged: list[tuple[datetime, datetime]] = []
    for s, e in busy:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def find_candidate_slots(
    *,
    participants: list[Participant],
    date_range_start: date,
    date_range_end: date,
    duration_minutes: int,
    owner_events_by_day: dict[date, list[dict[str, Any]]],
    owner_timezone: str,
    config: ScoringConfig | None = None,
    top_n: int | None = None,
) -> list[TimeSlot]:
    """Find and score the best meeting slots. Pure function — no I/O.

    `owner_events_by_day`: caller (coordinator) fetches the owner's calendar
    events for each day in range and passes them as a dict[date, list[event]].
    """
    config = config or ScoringConfig()
    top_n = top_n or config.top_n

    all_candidates: list[TimeSlot] = []
    events_per_day: dict[date, int] = {}
    all_busy: list[tuple[datetime, datetime]] = []

    current = date_range_start
    while current <= date_range_end:
        if current.weekday() >= 5:  # skip Sat/Sun
            current += timedelta(days=1)
            continue

        events = owner_events_by_day.get(current, [])
        busy = events_to_busy_intervals(events, owner_timezone)
        events_per_day[current] = len(events)
        all_busy.extend(busy)

        raw_slots = _generate_raw_slots(current, duration_minutes, participants, config)
        for start_utc, end_utc in raw_slots:
            conflict = _find_conflict(start_utc, end_utc, busy)
            score = compute_score(
                start_utc, end_utc, participants,
                busy, events_per_day,
                date_range_start, date_range_end,
                owner_tz=owner_timezone,
                requires_move=conflict, config=config,
            )
            all_candidates.append(TimeSlot(
                start_time=start_utc, end_time=end_utc,
                score=score, requires_move=conflict,
            ))
        current += timedelta(days=1)

    all_candidates.sort(key=lambda s: s.score, reverse=True)
    deduped = _deduplicate_overlapping(all_candidates)
    return deduped[:top_n]
