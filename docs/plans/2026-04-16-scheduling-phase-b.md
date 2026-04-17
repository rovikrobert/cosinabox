# Plan: Scheduling Phase B

**Date:** 2026-04-16
**Status:** Completed 2026-04-16.
**Precursors:** PRs #17 (Plan 4C kickoff), #18 (dedup + stress suite), #19 (security), #20 (correctness), #22 (fresh-calendar rescore band-aid).
**Worktree target:** `~/.worktrees/cantina/scheduling-phase-b` (create at M1).

---

## Context / Why

Phase A shipped a working group-scheduling sub-system: an 8-state machine, 30-min polling job, 6-dimensional slot scorer, Gmail + Telegram outreach, Sonnet response parser, and a 41-test stress suite. It works end-to-end, but a stale-score bug surfaced in PR #22 forced a band-aid: `find_consensus` re-scores qualifying slots against "fresh" owner calendar events because the stored scores (computed at PROPOSING time, up to 48h earlier) go stale while the owner accepts new meetings that overlap proposed slots.

The fix currently threads a raw `dict[date, list[event_dict]]` through three layers:

1. `app.py` builds `tool_instances` (including the Google Calendar adapter) and stashes it in `scheduling_ctx["coordinator_ctx"]["gmail"]` / passes `tool_instances.get("calendar")` directly into `SchedulingPollCheckJob`.
2. `jobs/scheduling_poll_check.py` imports the private helper `_fetch_owner_events_for_slots` from the coordinator, calls it per request, and passes the resulting dict into `find_consensus`.
3. `scheduling/coordinator.py:find_consensus` branches on `owner_events_by_day is None` — skip fresh re-score vs. compute busy intervals + `compute_score` per qualifying slot.

This is brittle for several concrete reasons:

- **Leaky abstraction.** The `jobs` layer reaches into a private coordinator helper (`_fetch_owner_events_for_slots`) and reshapes calendar adapter output into the Google Calendar event dict shape that `slot_scorer.events_to_busy_intervals` expects. Any calendar adapter that isn't Google-shaped will silently produce empty busy intervals and re-introduce the stale-score bug.
- **Duplicated fetch.** `check_polling_status` already calls `_fetch_owner_events_for_slots`, and then the poll job calls it *again* on the same request before calling `find_consensus` a second time. Every polling cycle for every active request pays 2× the calendar-list API cost.
- **Untestable contract.** The rescore path has no explicit protocol — there's no "CalendarProvider" interface to stub, so tests either pass pre-shaped dicts (hiding the adapter-shape bug) or mock `list_events` to return objects with `.start`/`.end` (exercising one of two code paths).
- **Owner-identity coupling.** `owner_timezone` and owner calendar are threaded by position through six function signatures. Multi-owner scheduling (explicitly a non-goal here, see below) is impossible, but even *tests* of cross-timezone fairness have to reconstruct the owner context by hand.

The scheduling retro flagged this as Phase B's primary target: **"promote fresh-calendar scoring from band-aid to first-class; decouple owner-event injection."**

---

## What Phase A left on the table

From Plan 4C documentation and in-code comments:

1. **Calendar event creation on `book`.** `coordinator.record_decision("book")` returns `phase_b_note: "Calendar event creation is deferred to Phase B. Please create the event manually..."`. Same TODO in `scheduling_tool.py`'s `_BOOK_PHASE_B_CAVEAT` and the docstring of `coordinator.py` ("Calendar-event booking is deferred to Phase B (Plan 5)"). **This is the highest-visibility Phase A deferral** — the loop is not closed until the engine writes the calendar event.
2. **Direct-to-participant Telegram DMs for nudges.** `jobs/scheduling_poll_check.py` has an explicit OSS caveat: *"Sending a Telegram DM directly to the participant is an app-level concern (Phase B)."* Today, nudge/expire messages go to `send_fn` (the owner's DM), not the participant.
3. **Calendar-adapter contract.** `_fetch_owner_events_for_slots` hardcodes `calendar.list_events(start=datetime, end=datetime)` with `.start`/`.end` attributes, re-shaping them into Google-style event dicts. The adapter protocol was never formalised.
4. **Rescore staleness beyond the consensus moment.** Fresh-calendar rescore runs only at `find_consensus` time. Slot scores shown in `scheduling_status` (owner tool) are still the stored, possibly-stale values. An owner reviewing mid-polling sees scores that no longer reflect reality.
5. **Dedicated `nudged_at` column.** `jobs/scheduling_poll_check.py` comment: *"no dedicated nudged_at column exists — the status flip guards against re-nudging."* The bot-down-during-nudge-window recovery path (72h safety cap) would be cleaner with a real timestamp than with the status-flip proxy.
6. **`backchannel.py` full move-engine wiring.** Priority classification + move-proposal logic is implemented, but the state machine's BACKCHANNEL state is never entered by any polling-time code path — only by explicit owner action (which has no tool handler exposed). The backchannel engine is effectively dead code in the runtime.
7. **Participant-side response parsing robustness.** `parse_response` returns `{"error": ...}` or `{"counter_proposal": ...}` for malformed or out-of-band replies, but the polling job just logs them as `parse_errors` and returns. There's no owner-facing escalation, and no record in the DB that a parse failure occurred for a given participant.

---

## Non-goals (explicit)

Kept out of Phase B to prevent scope creep:

- **Multi-stakeholder scheduling beyond 1:1-with-owner + N participants.** Owner remains the single "host" whose calendar and timezone are authoritative.
- **New communication channels** (Slack, SMS, WhatsApp). Gmail + Telegram only.
- **New scheduling UI.** No web UI, no Telegram bot commands beyond existing inline-keyboard callbacks. Owner interacts via the 3 existing tools (`schedule_group_meeting`, `scheduling_status`, `scheduling_respond`) and DM replies.
- **Rewriting the scorer.** `slot_scorer.py` weights, dimensions, and hard-block stay as-is. Phase B is about *when* scoring runs and *what inputs it sees*, not *how it scores*.
- **Migrating away from SQLite.** Memory class, WAL mode, schema all preserved.
- **Async rewrite.** Sync throughout, per the OSS discipline.
- **Auto-proposing backchannel moves.** The existing `backchannel.py` stays opt-in via owner action; automated move proposals during polling are out of scope (requires user trust we haven't earned).

---

## Target architecture

**Single abstraction:** `SchedulingContext` — a frozen dataclass built once at app-wire time, passed through to every coordinator entry point. It owns:

- `db: Memory` — the scheduling DB handle.
- `owner: OwnerProfile` — `name`, `timezone`, `email` (for self-exclusion from participants).
- `calendar: CalendarProvider | None` — see below.
- `gmail: GmailProvider | None` — already exists informally, typed here.
- `bot: SchedulingBotAdapter | None` — the sync Telegram adapter (Plan 4C).
- `anthropic_client`, `cost_tracker` — same as today.
- `scoring_config: ScoringConfig` — lifted from per-call kwarg to context attribute.

**New protocol:** `CalendarProvider` (Python `typing.Protocol`) with exactly the methods scheduling needs:

```python
class CalendarProvider(Protocol):
    def list_busy_intervals(
        self,
        *,
        start: datetime,
        end: datetime,
        timezone: str,
    ) -> list[BusyInterval]: ...

    def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        attendees: list[str],
        description: str | None = None,
    ) -> CreatedEvent: ...
```

`BusyInterval` is a small dataclass (`start: datetime, end: datetime, source_event_id: str | None`). The protocol is narrower than today's `list_events` — it returns pre-shaped intervals, so `slot_scorer.events_to_busy_intervals` stops being load-bearing on raw Google dicts. The Google Calendar adapter in `tools/google/` gets a thin `GoogleCalendarProvider` wrapper that implements this protocol; tests get a `FakeCalendarProvider`.

**Consequence for `find_consensus`.** Signature becomes:

```python
def find_consensus(ctx: SchedulingContext, request_id: str) -> TimeSlot | None:
```

No more `owner_events_by_day` kwarg. The function calls `ctx.calendar.list_busy_intervals(...)` itself when re-scoring. The `None` (skip fresh rescore) branch collapses into "ctx.calendar is None, use stored scores."

**Consequence for `check_polling_status` and `SchedulingPollCheckJob`.** Both stop reaching into `_fetch_owner_events_for_slots`. The private helper is deleted. The poll job's single coordinator call (`check_polling_status`) returns the consensus slot directly, eliminating the duplicate calendar fetch.

**Consequence for `book`.** With `ctx.calendar` available, `record_decision("book", ...)` can finally call `ctx.calendar.create_event(...)` to close Phase A's deferral. Gated by `ctx.calendar is not None` with a clear error when missing.

**Consequence for `app.py`.** `scheduling_ctx` stops being a loose dict. It becomes a `SchedulingContext` built by a single helper (`cosinabox.scheduling.context.build_from_integrations`). The tool registry receives the typed context; `SchedulingPollCheckJob` receives the typed context. One construction site, one passing convention.

---

## Milestones

Each milestone is an independently-reviewable PR. Full pytest suite (627 tests) MUST stay green at the head of every PR. Stress suite (`tests/stress/test_plan4c_stress.py`) runs on every PR.

### - [x] M1: Introduce `SchedulingContext` + `CalendarProvider` protocol (no behaviour change)

- **Files touched:**
  - Create `src/cosinabox/scheduling/context.py` (`SchedulingContext` dataclass, `OwnerProfile`, `CalendarProvider` Protocol, `BusyInterval` / `CreatedEvent` dataclasses, `build_from_integrations(integrations, memory, ...) -> SchedulingContext`).
  - `src/cosinabox/scheduling/__init__.py` — export new names.
  - Create `tests/unit/test_scheduling_context.py` (construction, default-fallback, frozen-ness, None-calendar behaviour).
- **Tests:** new unit suite + existing 627 tests unchanged (no wiring yet).
- **Risk / rollback:** zero runtime impact — purely additive. Revert = delete the two new files.

**Estimate:** 1 hr.

### - [x] M2: Wire `CalendarProvider` into `find_consensus` (parity behaviour)

- **Files touched:**
  - `src/cosinabox/scheduling/coordinator.py` — new overload `find_consensus(ctx, request_id)` alongside the existing `find_consensus(db, request_id, owner_events_by_day=...)`. New one calls `ctx.calendar.list_busy_intervals` internally. Old one kept as a shim that constructs an ad-hoc `SchedulingContext` from its kwargs (deprecation warning via `warnings.warn`).
  - `src/cosinabox/scheduling/slot_scorer.py` — add `busy_intervals_to_tuples(intervals: list[BusyInterval]) -> list[tuple[datetime, datetime]]` so `compute_score` doesn't have to change.
  - `src/cosinabox/tools/google/calendar.py` (or wherever the adapter lives) — implement `GoogleCalendarProvider` wrapping the existing `list_events` call.
  - `tests/unit/test_scheduling_coordinator.py` — add cases using the new signature with a `FakeCalendarProvider`.
  - `tests/stress/test_plan4c_stress.py` — add one stress test: `test_find_consensus_calls_provider_once_per_cycle`.
- **Tests:** new tests + existing stress suite passes unchanged through the deprecation shim.
- **Risk / rollback:** deprecation shim means old callers still work. Rollback = revert the file; shim-only callers don't see a change.

**Estimate:** 2 hr.

### - [x] M3: Migrate `check_polling_status` + `SchedulingPollCheckJob` to the context; delete duplicate fetch

- **Files touched:**
  - `src/cosinabox/scheduling/coordinator.py` — `check_polling_status(ctx, request_id)` new signature; internally calls the new `find_consensus(ctx, ...)` exactly once; returns the consensus slot in its return dict. Delete `_fetch_owner_events_for_slots` (no callers left after M3).
  - `src/cosinabox/jobs/scheduling_poll_check.py` — constructor takes `SchedulingContext`; removes the private-helper import; no more second `find_consensus` call — uses the slot that `check_polling_status` returns.
  - `src/cosinabox/app.py` — `scheduling_ctx` construction replaced by `build_from_integrations(...)`. `SchedulingPollCheckJob(...)` call site updated.
  - `src/cosinabox/tools/scheduling_tool.py` — `build_scheduling_handlers(ctx: SchedulingContext)` instead of the kwargs explosion. Handlers forward `ctx` to coordinator calls.
  - `src/cosinabox/tools/registry.py` — tool registry accepts `SchedulingContext` instead of the dict shape.
  - `tests/stress/test_plan4c_stress.py` — all coordinator calls updated to the new signature; `FakeCalendarProvider` replaces the current `calendar.list_events` MagicMock pattern.
- **Tests:** full 627 suite must stay green. Add 3 new stress tests: duplicate-fetch-prevention, provider-call-count, poll-job-with-None-calendar-graceful-fallback.
- **Risk / rollback:** this is the breaking change. Rollback requires reverting 5 files. Gate: M1 + M2 must have been merged and stable for at least one polling cycle in the reference deployment (`rovik-keevs`) before M3 ships.

**Estimate:** 4 hr (largest milestone).

### - [x] M4: Remove the deprecation shim + `owner_events_by_day` kwarg

- **Files touched:**
  - `src/cosinabox/scheduling/coordinator.py` — delete the old `find_consensus(db, request_id, owner_events_by_day=...)` signature + its `warnings.warn`.
  - Search codebase for any remaining `owner_events_by_day=` callers and convert / delete.
- **Tests:** full suite green; grep confirms zero remaining uses of the old kwarg.
- **Risk / rollback:** Low — M3 has already removed all in-tree callers. Risk is third-party integrators on the deprecated signature; this is why M3 and M4 are separate PRs with at least one release gap.

**Estimate:** 30 min.

### - [x] M5: Close the `book` loop — calendar event creation

- **Files touched:**
  - `src/cosinabox/scheduling/coordinator.py` — `record_decision("book", ...)` calls `ctx.calendar.create_event(...)`. Writes the returned event ID into a new `scheduling_requests.booked_event_id` column (migration).
  - `src/cosinabox/memory/sqlite.py` — schema migration for `booked_event_id TEXT NULL`.
  - `src/cosinabox/migrations/` — add migration file.
  - `src/cosinabox/scheduling/models.py` — `SchedulingRequest.booked_event_id: str | None = None`.
  - `src/cosinabox/tools/scheduling_tool.py` — drop `_BOOK_PHASE_B_CAVEAT`; success message now says "Created calendar event {event_id}."
  - `src/cosinabox/tools/google/calendar.py` — `GoogleCalendarProvider.create_event` implementation.
  - `tests/stress/test_plan4c_stress.py` — new test `test_book_creates_calendar_event` and `test_book_fails_gracefully_when_calendar_missing`.
- **Tests:** full suite green + 2 new stress tests. Manual smoke: book one real request end-to-end on `rovik-keevs`.
- **Risk / rollback:** calendar writes are a real external side effect. Guard with a `dry_run: bool = False` parameter on the provider and a config flag `scheduling.book_creates_event: bool` (default `True` but can be toggled off per deployment). Rollback plan: config flag off + migration is additive (nullable column), so revert is safe.

**Estimate:** 2 hr.

### - [x] M6: `nudged_at` column + participant-channel DM nudges

- **Files touched:**
  - `src/cosinabox/memory/sqlite.py` + `migrations/` — new `scheduling_participants.nudged_at TIMESTAMP NULL` column.
  - `src/cosinabox/scheduling/db.py` — `record_nudge(db, participant_db_id, channel_target)` + update existing `update_participant_status` callers.
  - `src/cosinabox/jobs/scheduling_poll_check.py` — nudge path uses the participant's channel (gmail draft to `p.email` / Telegram DM to `p.telegram_id`) instead of `send_fn(text)` to the owner. `send_fn` still used for owner-visibility summary.
  - `tests/stress/test_plan4c_stress.py` — nudge-channel-routing test + nudged_at-timestamp test.
- **Tests:** full suite + 2 new stress tests.
- **Risk / rollback:** sending DMs directly to third parties is higher-stakes than the current owner-only summary. Gate M6 behind a config flag `scheduling.nudge_participants_directly: bool` (default `False` — explicit opt-in). Rollback = flag off.

**Estimate:** 2 hr.

---

## Test impact

- **`tests/stress/test_plan4c_stress.py` stays load-bearing.** All 41 existing tests updated in M3 to use `SchedulingContext` + `FakeCalendarProvider`. No test is deleted. 7 new tests added across M2–M6 (one per milestone's guarantees).
- **New fixture:** `tests/stress/fixtures.py` — `FakeCalendarProvider` with configurable busy intervals and `create_event` capturing calls for assertion. Replaces the current MagicMock-per-test pattern.
- **Regression harness:** one stress test per phase-B failure mode we've already seen: (a) stale stored score beats fresh zero-score slot, (b) calendar adapter without `list_events` — provider protocol forces correct fallback, (c) `book` called when `ctx.calendar is None` returns a clean error instead of crashing.
- **Pytest target:** `pytest -q` and `pytest tests/stress -q` both green at the head of every PR. 627 → 634 tests by end of M6.

---

## Risks

1. **In-flight scheduling requests during deploy.** Polling windows are 48h. A deploy mid-Phase-B migration must not corrupt an in-progress request. Mitigation: every milestone preserves the DB schema shape (M5, M6 add nullable columns only); coordinator-signature changes in M2–M4 go through the deprecation shim so rolling restarts see zero API breaks.
2. **Calendar-provider contract drift.** If the Google adapter evolves to return `BusyInterval` subtly differently (e.g., all-day events), the scorer gets wrong inputs silently. Mitigation: `CalendarProvider` protocol is explicit about timezone-awareness and all-day handling in its docstring; a stress test asserts that all-day events are treated as full-day busy.
3. **Real calendar writes in M5.** The `book` → `create_event` path has real external side effects. Mitigation: `dry_run` provider flag + config gate + manual smoke test on `rovik-keevs` before rollout to any other deployment.
4. **Third-party DMs in M6.** Sending Telegram messages to participants' IDs from the engine, not the owner's account, is a trust boundary. Mitigation: opt-in flag defaulting off; explicit participant consent check TBD (open question).
5. **Duplicate-consensus race.** M3 removes the redundant `find_consensus` call; if two concurrent polling cycles fire (cron overlap or manual trigger), the optimistic-concurrency guard in `transition` already handles it. Verify with a stress test that spins 2 threads calling `check_polling_status` simultaneously.
6. **`scheduling_status` still shows stale scores.** Not in M1–M4 scope. Decide in open questions whether to add on-read rescore for owner tools.

---

## Open questions

1. **On-read rescore for `scheduling_status`.** Should the owner-facing status tool rescore against the current calendar (adding latency + a Sonnet call per invocation) or continue to show stored scores (faster, but stale mid-polling)?
2. **Participant-consent for direct DMs.** Is there a prior interaction or opt-in the engine should require before the M6 nudge path sends a Telegram DM to a participant we've never messaged before?
3. **Backchannel move engine (Phase A item 6).** Wire backchannel into the polling job as a Phase B deliverable, or defer to Phase C? Current plan defers.
4. **Cross-timezone fairness edge cases.** The retro mentioned these — specifically, do hard-block boundaries shift around DST? The scorer already checks prev/current/next day for DST boundaries in `compute_overlap_window`. Is there a concrete failing test case to add, or is this concern handled?
5. **Should `SchedulingContext` be immutable (`frozen=True`)?** Mutable means test setup can hot-swap the provider; immutable means `app.py` wiring is the single point of truth. Leaning frozen + `replace()` helper.
