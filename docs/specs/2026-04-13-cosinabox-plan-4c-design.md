# Plan 4C: Scheduling Sub-System

**Date:** 2026-04-13
**Status:** Design approved
**Depends on:** Plan 4A (memory client, structured logging), Plan 4B (SubAgent — optional)
**Estimated effort:** ~20h across 10 files

## Context

Plan 4C is a direct port of cos-agent's battle-tested scheduling sub-system (3,194 lines). It enables multi-person meeting coordination: user says "find time for me and Alice and Bob next week" → system generates optimal slots across timezones, presents to user for approval, coordinates outreach via Telegram/Gmail, parses responses, converges on consensus, books the meeting.

**Design principles:**
1. Port from cos-agent — this is production-tested, don't rewrite
2. OSS-friendly — no hardcoded user names, stakeholder domains, or timezones in the engine
3. State machine enforces safety — invalid transitions raise exceptions
4. Human-in-loop — Gmail outreach is always drafted, user reviews before sending
5. **Sync throughout** — cos-agent is async (aiosqlite, async coordinator). Cosinabox is sync (sqlite3, BackgroundScheduler). The port converts to sync: `scheduling/db.py` uses sync `sqlite3`, coordinator functions are sync, polling job runs in a BackgroundScheduler thread directly. This matches existing cosinabox conventions and avoids `asyncio.run()` inside threads (which creates fresh event loops per fire).
6. **Model ID from defaults** — all Sonnet calls use `cosinabox.defaults.SONNET_MODEL_ID`, never hardcoded model strings. cos-agent's `claude-sonnet-4-5-20250514` gets replaced with `SONNET_MODEL_ID` ("claude-sonnet-4-6") during port.

## Components

### 1. State Machine

**8 states, 7 valid transitions:**

```
PROPOSING → ROVIK_REVIEW → POLLING → CONVERGED → BOOKED
            ↘ BACKCHANNEL ↗         ↘ ROVIK_REVIEW (no consensus)
```

Terminal states: `BOOKED`, `CANCELLED`, `EXPIRED`.

The `_TRANSITIONS` dict enforces legal moves. Invalid transitions raise `InvalidTransition`.

### 2. Data Model (5 SQLite tables)

```sql
scheduling_requests (id, title, duration, date_range, status, preferred_timezone, notes, created_at, updated_at)
scheduling_participants (id, request_id, name, email, telegram_id, timezone, channel, status, gmail_thread_id, gmail_draft_id, outreach_sent_at, created_at)
scheduling_slots (id, request_id, start_time, end_time, score, requires_move, move_approved, created_at)
scheduling_responses (id, request_id, participant_id, slot_id, response, responded_at)
scheduling_moves (id, request_id, event_id, original_start/end, new_start/end, undone, created_at)
```

All stored in the same `.cosinabox/memory.db` as conversation memory and logging.

### 3. Slot Scorer (6 dimensions)

Weights (must sum to 1.0):
- **Timezone fairness (30%)** — penalizes slots outside 8am-7pm for any participant
- **Owner preference (25%)** — configurable time-of-day preferences (default: peak 9am-12pm, lunch 12-1pm avoided, afternoon 1-6pm good)
- **Buffer time (15%)** — 30+ min buffer before/after existing events
- **Move cost (15%)** — no move = 1.0, requires moveable conflict = 0.5
- **Day balance (10%)** — fewer existing meetings that day = higher score
- **Recency (5%)** — slight preference for sooner dates

**Hard block:** 1am-6am local time for any participant — never propose.

### 4. Backchannel / Move Engine

When a top-scoring slot conflicts with an existing event, classify priority:
- **Immovable:** Configurable keyword list (defaults: "board meeting", "investor", "visa", "government"), VIP domains, events within 24h
- **High priority:** Configurable (defaults: "1:1", "partner", "client"), 3+ external attendees
- **Low priority:** "focus block", "tentative", "hold" — candidates for moving

Proposes moving low-priority events (max 2 per request) with alternative times. User approves/rejects each move. Approved moves execute during `book_slot` action. Undo log enables reversal on cancellation.

### 5. Outreach

**Telegram channel:** Immediate send with inline keyboard (one button per slot). User clicks → real-time response capture via callback handler.

**Gmail channel:** Creates draft (never auto-sends). User reviews + sends manually. Responses captured by polling job every 30 min via thread read.

### 6. Response Parser

Sonnet call parses natural language responses:
```
Return JSON: {"responses": {"<slot_id>": "yes"|"if_needed"|"no", ...}}
         OR  {"counter_proposal": "..."}
         OR  {"error": "..."}
```

Telegram inline button responses bypass Sonnet — direct mapping from `callback_data`.

**Cost tracking:** Each Sonnet call in `response_parser.py` records cost via `CostTracker.record()` using `estimate_cost(SONNET_MODEL_ID, input_tokens, output_tokens)` — same pattern as Plan 4B's extraction jobs. A heavily active scheduling cycle (10 polls × 5 participants) could generate 50+ Sonnet calls, and all must appear in `/cost` and `daily_costs`.

### 7. Polling Job

Runs every 30 minutes (`scheduling_poll_check`):
1. Get all requests in POLLING status
2. For each: fetch Gmail replies, parse, store responses
3. Check consensus (all "yes" or "if_needed" on any slot) → CONVERGED
4. Nudge at 24h no response, expire at 48h
5. If all expired → ROVIK_REVIEW (user decides)

### 8. Tools (3 exposed to agent)

- `schedule_group_meeting` — start flow with title, duration, participants, date range
- `scheduling_status` — check a request's state
- `scheduling_respond` — user actions: approve_slots, approve_move, reject_move, book_slot, cancel, add_constraint

## OSS Adaptations

The cos-agent code has several hardcoded values that need to be generalized for OSS:

### 1. No hardcoded user names

cos-agent has "Rovik" throughout. Engine version uses `name` from `personality.md`. In prompts and messages, use `name` variable, not "Rovik".

### 2. Configurable immovability / priority

cos-agent has hardcoded keyword lists ("edb", "daniel", "ntu"). Engine version reads these from `integrations.yaml`:

```yaml
scheduling:
  immovable_keywords: ["board meeting", "investor", "visa", "government", "legal"]
  high_priority_keywords: ["1:1", "partner", "client"]
  vip_domains: []  # user adds their own (e.g. ".gov", "@client.com")
```

Empty defaults are safe — everything is medium priority unless the user explicitly configures.

### 3. Configurable timezone mapping

cos-agent has hardcoded domain→timezone mappings ("cantina.ai" → "America/Montreal"). Engine uses generic domain/org mappings from `integrations.yaml`:

```yaml
scheduling:
  domain_timezones:
    # Map email domains to IANA timezones for participants without explicit tz
    # Example:
    # "example.com": "America/Los_Angeles"
```

Default: empty dict → falls back to user's default timezone from `personality.md`.

### 4. Configurable time preferences

cos-agent has hardcoded "peak 9am-12pm" for Rovik. Engine exposes this in config:

```yaml
scheduling:
  peak_hours: [9, 12]          # 9am-12pm scores 1.0
  avoid_hours: [12, 13]        # lunch — scores 0.2
  workday_hours: [9, 18]       # outside this = 0.3
```

Defaults match cos-agent's profile (reasonable for knowledge workers).

### 5. Telegram inline keyboard callback

New callback handler for `callback_data` starting with `sched_resp:`. Implementation:

1. Extend `src/cosinabox/bot/telegram.py` with a `register_callback_handler(prefix: str, fn: Callable)` method. Internally wraps `CallbackQueryHandler` with a pattern filter on `callback_data`.
2. `App.run()` calls `tg_app.add_handler(CallbackQueryHandler(handle_scheduling_callback, pattern=r"^sched_resp:"))` after the existing command handlers.
3. The handler parses `sched_resp:{request_id}:{participant_id}:{slot_id}` → records response in `scheduling_responses` table → answers the callback query with a confirmation toast.

This is the first `CallbackQueryHandler` in cosinabox — the existing bot module only handles `MessageHandler` and `CommandHandler`.

### 6. Tool definitions built dynamically

cos-agent's `TOOL_DEFINITIONS` is a static list with "Rovik" and "Keevs" in descriptions. For OSS, wrap in a builder function:

```python
# src/cosinabox/tools/scheduling_tool.py
def build_scheduling_tool_definitions(owner_name: str) -> list[dict]:
    return [
        {
            "name": "schedule_group_meeting",
            "description": (
                "Start a group scheduling flow. Finds optimal times across "
                "all participant timezones (excluding 1am-6am for everyone), "
                f"presents options to {owner_name} first, then coordinates "
                "via Telegram/Gmail to find consensus."
            ),
            # ...
        },
        # ...
    ]
```

`build_tool_registry` accepts `owner_name=name` and passes to this builder.

## Files

**New files:**
- `src/cosinabox/scheduling/__init__.py`
- `src/cosinabox/scheduling/models.py` — dataclasses + SchedulingStatus enum
- `src/cosinabox/scheduling/db.py` — SQLite CRUD operations
- `src/cosinabox/scheduling/participant.py` — timezone/channel resolution
- `src/cosinabox/scheduling/slot_scorer.py` — 6-dim scoring + overlap computation
- `src/cosinabox/scheduling/backchannel.py` — priority classification + move engine
- `src/cosinabox/scheduling/response_parser.py` — Sonnet-based NL parser
- `src/cosinabox/scheduling/outreach.py` — Telegram + Gmail outreach
- `src/cosinabox/scheduling/coordinator.py` — state machine + flow orchestration
- `src/cosinabox/jobs/scheduling_poll_check.py` — 30-min polling job
- `src/cosinabox/tools/scheduling_tool.py` — 3 Claude tool definitions + handlers
- `src/cosinabox/bot/scheduling_callbacks.py` — Telegram callback handler for inline buttons
- `src/cosinabox/templates/user-repo/docs/agent/scheduling.md` — user-facing docs
- 8 test files (models, db, slot_scorer, backchannel, response_parser, coordinator, polling, tool)

**Modified files:**
- `src/cosinabox/memory/sqlite.py` — add 5 scheduling tables to `_SCHEMA`
- `src/cosinabox/tools/registry.py` — register scheduling tools
- `src/cosinabox/app.py` — instantiate scheduling infra, register job + callback handler
- `src/cosinabox/templates/user-repo/integrations.yaml` — add `scheduling` section (all optional, empty defaults)
- `src/cosinabox/templates/user-repo/jobs.yaml` — add `scheduling_poll_check` (disabled by default)
- `src/cosinabox/templates/user-repo/docs/agent/jobs.md` — document scheduling
- `src/cosinabox/prompts/core.py` — add scheduling to Capabilities

## Testing Strategy

| Component | Test file | Key cases |
|-----------|-----------|-----------|
| State machine | `test_scheduling_coordinator.py` | All 8×8 = 64 transition pairs tested: 7+ succeed, rest raise `InvalidTransition`. State persistence across process restart. |
| Data model | `test_scheduling_db.py` | CRUD on all 5 tables, foreign keys, status enum validation |
| Slot scorer | `test_scheduling_scorer.py` | 6-dim scoring, hard block 1am-6am, multi-timezone overlap, empty participants |
| Backchannel | `test_scheduling_backchannel.py` | Priority classification (all 3 levels), move proposal generation, max 2 moves |
| Response parser | `test_scheduling_response_parser.py` | Sonnet returns "yes/if_needed/no", counter_proposal, error, malformed JSON |
| Outreach | `test_scheduling_outreach.py` | Gmail draft creation, Telegram poll with keyboard, multi-channel mix |
| Polling job | `test_scheduling_poll.py` | No active → skip, gmail reply detected, 24h nudge, 48h expire, consensus → CONVERGED |
| Tools | `test_scheduling_tool.py` | schedule_group_meeting creates request, scheduling_status formats output, scheduling_respond transitions |

**Stress test checklist:**
- First run (empty tables) — no crash
- No fireflies/attio/etc — scheduling still works (Google Calendar only required dep)
- Participant without email or telegram_id — skipped with clear log
- All participants have same timezone — overlap is trivial, don't over-engineer
- Hard block 1am-6am — no slots proposed in that window for any timezone
- State machine: attempt illegal transitions → raises
- Polling job: meeting happens in middle of window → result consistent
- Moves: approved move cancelled later → original time restored

## What's Deferred to Plan 5

- Actual calendar event creation on BOOKED (currently stops at state transition — Phase B)
- Move execution against real calendar (library has logic, but needs wiring to real GCal API)
- These are small (~2h) but require live calendar testing

**User-facing disclosure:** `docs/agent/scheduling.md` MUST include a "Current limitations" section:
> **Phase B deferred:** When you `book_slot`, the state transitions to BOOKED but the calendar event is not yet created automatically. You'll see the agreed slot in the `scheduling_status` output — create the event manually in Google Calendar until Plan 5 wires this up.

The `book_slot` action's response text also includes this caveat so users see it at the point of action, not just in docs.
