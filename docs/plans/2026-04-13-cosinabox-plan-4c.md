# Plan 4C: Scheduling Sub-System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan.

**Goal:** Port cos-agent's 10-file scheduling sub-system to cosinabox, converting async→sync and making OSS-friendly.

**Architecture:** State machine (PROPOSING→ROVIK_REVIEW→POLLING→CONVERGED→BOOKED) with SQLite persistence, 6-dimensional slot scoring, backchannel move engine, Gmail+Telegram outreach, Sonnet response parser, 30-min polling job.

**Tech Stack:** Python 3.11+, sync sqlite3, Anthropic Sonnet, APScheduler, python-telegram-bot

**Spec:** `docs/superpowers/specs/2026-04-13-cosinabox-plan-4c-design.md`

**Worktree:** `~/.worktrees/cantina/plan4c-scheduling`

**Source to port:** `~/Cantina/cos-agent/src/scheduling/` + `src/tools/scheduling_tool.py` + `src/scheduler/scheduling_jobs.py`

---

### Task 1: Schema + models + db layer

**Files:**
- Modify: `src/cosinabox/memory/sqlite.py` (append 5 scheduling tables to `_SCHEMA`)
- Create: `src/cosinabox/scheduling/__init__.py` (empty + exports)
- Create: `src/cosinabox/scheduling/models.py` (dataclasses + enum)
- Create: `src/cosinabox/scheduling/db.py` (sync CRUD operations)
- Test: `tests/unit/test_scheduling_db.py`

**Schema to append** (see spec — `scheduling_requests`, `scheduling_participants`, `scheduling_slots`, `scheduling_responses`, `scheduling_moves` + indexes).

**Models:** `SchedulingStatus` enum + `Participant`, `TimeSlot`, `SchedulingRequest` dataclasses. Port verbatim from cos-agent, no changes.

**DB operations** (sync — reads/writes via `memory._conn`): `create_request`, `get_request(id)`, `update_request_status(id, status)`, `get_active_requests(status_filter)`, `add_participant`, `update_participant_status`, `add_slot`, `record_response`, `get_responses(request_id)`, `record_move`, `mark_move_undone`.

Tests: create request, round-trip read, status update, active requests filter, response recording, foreign key constraints.

Commit: `feat(scheduling): schema + models + sync DB layer`

---

### Task 2: Participant resolution

**Files:**
- Create: `src/cosinabox/scheduling/participant.py`
- Test: `tests/unit/test_scheduling_participant.py`

Port from cos-agent. Remove hardcoded domain→timezone mappings (keep only structure — OSS users add their own in `integrations.yaml` under `scheduling.domain_timezones`).

```python
def resolve_timezone(
    *, email: str | None,
    org: str | None,
    explicit_tz: str | None,
    default_tz: str,
    domain_map: dict[str, str] | None = None,
    org_map: dict[str, str] | None = None,
) -> str:
    """Resolution order: explicit → org match → domain match → default."""
    if explicit_tz and explicit_tz != default_tz:
        return explicit_tz
    if org and org_map:
        for key, tz in org_map.items():
            if key.lower() in org.lower():
                return tz
    if email and domain_map:
        domain = email.split("@")[-1].lower() if "@" in email else ""
        for key, tz in domain_map.items():
            if domain == key.lower() or domain.endswith(f".{key.lower()}"):
                return tz
    return default_tz


def resolve_channel(*, email: str | None, telegram_id: str | None) -> str:
    """telegram_id wins if present, else gmail if email present, else gmail default."""
    if telegram_id:
        return "telegram"
    return "gmail"
```

Tests: explicit tz wins, domain match, org match, fallback to default, empty maps don't crash.

Commit: `feat(scheduling): participant timezone + channel resolution`

---

### Task 3: Slot scorer + overlap

**Files:**
- Create: `src/cosinabox/scheduling/slot_scorer.py`
- Test: `tests/unit/test_scheduling_scorer.py`

Port 6-dim scoring + hard block + candidate finder. All hardcoded preferences move to config params (passed in by coordinator from `integrations.yaml`):

```python
@dataclass
class ScoringConfig:
    peak_hours: tuple[int, int] = (9, 12)      # 9am-12pm scores 1.0
    avoid_hours: tuple[int, int] = (12, 13)    # lunch scores 0.2
    workday_hours: tuple[int, int] = (9, 18)   # outside = 0.3
    hard_block: tuple[int, int] = (1, 6)       # 1am-6am NEVER propose

    # Weights (must sum to 1.0)
    w_timezone: float = 0.30
    w_owner_pref: float = 0.25
    w_buffer: float = 0.15
    w_move_cost: float = 0.15
    w_day_balance: float = 0.10
    w_recency: float = 0.05


def find_candidate_slots(
    *, participants: list[Participant],
    date_range_start: date,
    date_range_end: date,
    duration_minutes: int,
    owner_events: list[dict],
    owner_timezone: str,
    config: ScoringConfig = ScoringConfig(),
    top_n: int = 5,
) -> list[TimeSlot]:
    """Sync implementation. Ported from cos-agent's find_candidate_slots."""
```

Tests: hard block 1am-6am excluded for any participant tz; workday hours respected; scoring weights sum to 1.0; owner preference peaks at 9-12; top_n limits results; no slots when date range < duration.

Commit: `feat(scheduling): slot scorer with 6-dim weighted scoring + hard block`

---

### Task 4: Backchannel / move engine

**Files:**
- Create: `src/cosinabox/scheduling/backchannel.py`
- Test: `tests/unit/test_scheduling_backchannel.py`

Port priority classification + move proposal logic. Extract hardcoded keyword lists into config:

```python
@dataclass
class PriorityConfig:
    immovable_keywords: list[str] = field(default_factory=list)      # e.g., ["board meeting", "investor"]
    high_priority_keywords: list[str] = field(default_factory=list)  # e.g., ["1:1", "partner", "client"]
    low_priority_keywords: list[str] = field(default_factory=lambda: [
        "focus block", "focus time", "deep work", "tentative",
        "coworking", "hold", "blocked", "gym", "lunch", "break",
    ])
    vip_domains: list[str] = field(default_factory=list)             # e.g., [".gov", "@client.com"]
    max_moves_per_request: int = 2


def classify_priority(event: dict, config: PriorityConfig) -> str:
    """Returns 'immovable' | 'high' | 'medium' | 'low'."""
    # ... port logic, replace hardcoded keyword lists with config.*
```

Defaults: empty `immovable_keywords` / `high_priority_keywords` / `vip_domains` means the generic `low_priority_keywords` (focus, tentative, etc.) are the only guidance — safer than opinionated defaults.

Tests: priority classification for all 4 levels, empty config defaults to low/medium only, max 2 moves enforced, event within 24h always immovable.

Commit: `feat(scheduling): backchannel priority classification + move proposal engine`

---

### Task 5: Response parser

**Files:**
- Create: `src/cosinabox/scheduling/response_parser.py`
- Test: `tests/unit/test_scheduling_response_parser.py`

Port the Sonnet-based NL parser. **Critical fixes from stress test:**
- Use `cosinabox.defaults.SONNET_MODEL_ID` (not hardcoded model string)
- Record cost via `CostTracker.record()` after each Sonnet call
- Handle malformed JSON gracefully (return `{"error": "..."}`)

```python
def parse_response(
    *, participant_name: str,
    slots: list[TimeSlot],
    reply_text: str,
    anthropic_client: Any,
    cost_tracker: Any | None = None,
) -> dict[str, Any]:
    """Returns {'responses': {...}} or {'counter_proposal': '...'} or {'error': '...'}"""


def parse_callback_data(data: str) -> dict[str, Any]:
    """Parse Telegram inline button callback — no LLM. Format: sched_resp:{req_id}:{p_id}:{slot_id}"""
```

Tests: valid JSON response, counter_proposal, malformed JSON falls back to error, cost tracker called, callback parser handles 3-part and edge cases.

Commit: `feat(scheduling): response parser (Sonnet NL + callback data)`

---

### Task 6: Outreach (Telegram + Gmail)

**Files:**
- Create: `src/cosinabox/scheduling/outreach.py`
- Test: `tests/unit/test_scheduling_outreach.py`

Port both channels:

```python
def send_telegram_poll(
    *, bot: Any,
    participant: Participant,
    request: SchedulingRequest,
    slots: list[TimeSlot],
    owner_timezone: str,
) -> dict[str, Any]:
    """Send DM with inline keyboard. Returns {status: 'sent', message_id: ...}."""


def send_gmail_draft(
    *, gmail: Any,
    participant: Participant,
    request: SchedulingRequest,
    slots: list[TimeSlot],
    owner_name: str,
    owner_timezone: str,
) -> dict[str, Any]:
    """Create email draft (never auto-sent). Returns {status: 'draft_created', draft_id: ...}."""


def execute_outreach(
    *, request: SchedulingRequest,
    slots: list[TimeSlot],
    bot: Any | None,
    gmail: Any | None,
    owner_name: str,
    owner_timezone: str,
) -> str:
    """Iterate participants, dispatch to channel, update DB. Returns summary for owner."""
```

Tests: Telegram path creates inline keyboard with slot buttons, Gmail path creates draft, missing bot skips Telegram participants, missing gmail skips Gmail participants, all-no-channel returns error summary.

Commit: `feat(scheduling): Telegram + Gmail outreach`

---

### Task 7: Coordinator (state machine)

**Files:**
- Create: `src/cosinabox/scheduling/coordinator.py`
- Test: `tests/unit/test_scheduling_coordinator.py`

Port state machine + flow orchestration. `_TRANSITIONS` dict enforces 7 legal moves. All functions sync.

```python
_TRANSITIONS: dict[SchedulingStatus, set[SchedulingStatus]] = {
    SchedulingStatus.PROPOSING: {SchedulingStatus.ROVIK_REVIEW, SchedulingStatus.BACKCHANNEL, SchedulingStatus.CANCELLED},
    SchedulingStatus.ROVIK_REVIEW: {SchedulingStatus.POLLING, SchedulingStatus.PROPOSING, SchedulingStatus.CANCELLED},
    SchedulingStatus.POLLING: {SchedulingStatus.CONVERGED, SchedulingStatus.ROVIK_REVIEW, SchedulingStatus.EXPIRED, SchedulingStatus.CANCELLED},
    SchedulingStatus.BACKCHANNEL: {SchedulingStatus.PROPOSING, SchedulingStatus.ROVIK_REVIEW, SchedulingStatus.CANCELLED},
    SchedulingStatus.CONVERGED: {SchedulingStatus.BOOKED, SchedulingStatus.CANCELLED},
    SchedulingStatus.BOOKED: set(),
    SchedulingStatus.CANCELLED: set(),
    SchedulingStatus.EXPIRED: set(),
}


class InvalidTransition(Exception): pass


def transition(db: Any, request_id: str, from_status: SchedulingStatus, to_status: SchedulingStatus) -> None:
    if to_status not in _TRANSITIONS.get(from_status, set()):
        raise InvalidTransition(f"{from_status} → {to_status} is not allowed")
    # Update DB
```

Core flow functions: `start_scheduling(...)`, `check_polling_status(request_id)`, `find_consensus(request_id)`, `record_decision(request_id, action, **kwargs)`.

Tests: all 8×8 = 64 transition pairs (7 succeed, rest raise), `find_consensus` returns slot where all "yes"/"if_needed", `record_decision` dispatches actions correctly.

Commit: `feat(scheduling): coordinator state machine`

---

### Task 8: Polling job

**Files:**
- Create: `src/cosinabox/jobs/scheduling_poll_check.py`
- Test: `tests/unit/test_scheduling_poll.py`

Port `scheduling_poll_check` from cos-agent. Sync implementation running in APScheduler thread. 30-min cron.

```python
class SchedulingPollCheckJob(Job):
    name = "scheduling_poll_check"

    def __init__(self, *, db: Any, gmail: Any | None, anthropic_client: Any,
                 cost_tracker: Any | None, send_fn: Callable[[str], None]) -> None:
        ...

    def run(self, context: Any = None) -> str:
        # 1. Get all POLLING requests
        # 2. For each: check Gmail replies, parse via response_parser
        # 3. Check consensus → CONVERGED
        # 4. Nudge at 24h, expire at 48h
        # 5. If all expired → ROVIK_REVIEW
        # Returns: summary of actions taken
```

Tests: no active requests → "skipped", Gmail reply detected and parsed, 24h triggers nudge, 48h triggers expire, consensus found → CONVERGED.

Commit: `feat(scheduling): polling job — 30-min check for responses, nudges, expiry`

---

### Task 9: Tool definitions + handlers

**Files:**
- Create: `src/cosinabox/tools/scheduling_tool.py`
- Modify: `src/cosinabox/tools/registry.py` (register scheduling tools)
- Test: `tests/unit/test_scheduling_tool.py`

Dynamic tool builder:

```python
def build_scheduling_tool_definitions(owner_name: str) -> list[dict]:
    """3 tools: schedule_group_meeting, scheduling_status, scheduling_respond.
    owner_name is interpolated into descriptions (no hardcoded 'Rovik')."""


def build_scheduling_handlers(*, db, coordinator_ctx, owner_name, owner_timezone) -> dict[str, Callable]:
    """3 handlers that call coordinator functions. book_slot response includes
    the Phase B caveat: 'Calendar event creation is deferred — create manually.'"""
```

Register in `build_tool_registry(..., scheduling_ctx=None)`:

```python
if scheduling_ctx is not None:
    definitions.extend(build_scheduling_tool_definitions(scheduling_ctx["owner_name"]))
    handlers.update(build_scheduling_handlers(**scheduling_ctx))
```

Also add scheduling tools to policy `DEFAULT_RULES` as priority=200 ALLOW (these are owner actions, not external writes).

Tests: build definitions includes owner_name in descriptions, handlers dispatch to coordinator, book_slot response mentions Phase B limitation.

Commit: `feat(scheduling): Claude tools — schedule_group_meeting, status, respond`

---

### Task 10: Telegram callback handler

**Files:**
- Modify: `src/cosinabox/bot/telegram.py` (add `register_callback_handler()`)
- Create: `src/cosinabox/bot/scheduling_callbacks.py`
- Modify: `src/cosinabox/app.py` (wire callback handler)
- Test: `tests/unit/test_scheduling_callback.py`

Extend bot module:

```python
# bot/telegram.py
def register_callback_handler(self, prefix: str, fn: CallbackHandlerFn) -> None:
    self._callback_handlers.append((prefix, fn))
```

Callback handler:

```python
# bot/scheduling_callbacks.py
def build_scheduling_callback_handler(db: Any) -> Callable:
    async def handle_scheduling_callback(update: Update, _ctx: Any) -> None:
        data = update.callback_query.data  # "sched_resp:{req}:{pid}:{sid}"
        parsed = parse_callback_data(data)
        # record response in DB, answer callback with confirmation toast
    return handle_scheduling_callback
```

Wire in `App.run()` after existing handlers.

Tests: callback data parsing, response recorded in DB, answer_callback called.

Commit: `feat(scheduling): Telegram callback handler for inline button responses`

---

### Task 11: Wire into App.run() + OSS docs

**Files:**
- Modify: `src/cosinabox/app.py` (register scheduling job, build ctx, pass to registry)
- Modify: `src/cosinabox/templates/user-repo/jobs.yaml` (add `scheduling_poll_check`)
- Modify: `src/cosinabox/templates/user-repo/integrations.yaml` (add `scheduling:` config section)
- Create: `src/cosinabox/templates/user-repo/docs/agent/scheduling.md` (usage + Phase B limitation)
- Modify: `src/cosinabox/templates/user-repo/docs/agent/jobs.md` (add scheduling_poll_check)
- Modify: `src/cosinabox/prompts/core.py` (add scheduling to Capabilities)

Wire scheduling in app.py:
```python
# After memory_client is created
scheduling_ctx = {
    "db": memory,
    "gmail": gmail,
    "bot": None,  # Set after tg_app creation
    "owner_name": name,
    "owner_timezone": timezone,
    "anthropic_client": _Anthropic(),
    "cost_tracker": loop.cost,
}

# Pass to tool registry
tool_definitions, tool_handlers = build_tool_registry(
    tool_instances, timezone=timezone, rela_agent=rela_agent,
    scheduling_ctx=scheduling_ctx,
)

# Register polling job
elif job_name == "scheduling_poll_check":
    from cosinabox.jobs.scheduling_poll_check import SchedulingPollCheckJob
    job = SchedulingPollCheckJob(**scheduling_ctx, send_fn=send_telegram)
    cron = cfg.get("schedule", "*/30 * * * *")
    scheduler.add_job(job, cron=cron)
```

`integrations.yaml` addition:
```yaml
scheduling:
  # All fields optional. Empty = safe defaults.
  peak_hours: [9, 12]
  avoid_hours: [12, 13]
  workday_hours: [9, 18]
  immovable_keywords: []        # e.g., ["board meeting", "investor"]
  high_priority_keywords: []    # e.g., ["1:1", "partner"]
  vip_domains: []               # e.g., [".gov"]
  domain_timezones: {}          # e.g., {"example.com": "America/Los_Angeles"}
  max_moves_per_request: 2
```

`docs/agent/scheduling.md`:
```markdown
# Scheduling

Multi-person meeting coordination. You say "find time for me and Alice and Bob next week" and your CoS:
1. Finds optimal slots across all timezones (excludes 1-6am for everyone)
2. Shows you options, waits for approval
3. Sends polls via Telegram (internal team) or drafts emails (external)
4. Tracks responses every 30 min, nudges at 24h, expires at 48h
5. Surfaces consensus or escalates back to you for a decision

## Current limitations

**Phase B deferred to Plan 5:** When you book_slot, the state transitions to BOOKED but the calendar event is NOT yet created automatically. The agent will tell you the agreed time — create the event manually in Google Calendar until Plan 5 wires this up.

## Enabling scheduling

1. Enable the `scheduling_poll_check` job in `jobs.yaml`
2. Optionally configure `scheduling.*` in `integrations.yaml` (all defaults are safe)
3. Ask your CoS: "schedule a 45-minute meeting with Alice (alice@x.com, Europe/Berlin) and Bob (bob@y.com, telegram, tokyo) next week"
```

Commit: `feat(scheduling): wire into App + OSS docs + config`

---

### Task 12: Final validation

- Run full suite: `.venv/bin/pytest -q`. Target: 291 baseline + ~50 new = ~340+ passing.
- Stress checklist:
  - First run (empty tables) → no crash
  - Missing Fireflies/Attio → scheduling still works
  - No Calendar → start_scheduling returns clear error
  - State machine: illegal transition raises
  - Hard block 1am-6am verified
  - Cost tracker populated after parser Sonnet call
- Push, open PR, auto-merge, sync to rovik-keevs.

---

## Implementation Notes for Executor

- **Follow cos-agent code closely** — this is a port, not a rewrite. Use cos-agent files as reference:
  - `~/Cantina/cos-agent/src/scheduling/*.py`
  - `~/Cantina/cos-agent/src/tools/scheduling_tool.py`
  - `~/Cantina/cos-agent/src/scheduler/scheduling_jobs.py`
  - `~/Cantina/cos-agent/config/schema.sql` (scheduling tables)
- **Strip async throughout** — every `async def` becomes `def`, every `await` is removed, every `aiosqlite` call becomes `sqlite3` via `memory._conn`.
- **Replace hardcoded "Rovik"** with `owner_name` parameter. Replace hardcoded "SGT" with dynamic timezone display using `zoneinfo.ZoneInfo(tz).tzname()`.
- **Replace hardcoded Sonnet model** with `cosinabox.defaults.SONNET_MODEL_ID`.
- **Test between each task** — run `.venv/bin/pytest -q` before committing.
