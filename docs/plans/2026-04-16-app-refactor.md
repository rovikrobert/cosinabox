# Plan: Refactor `src/cosinabox/app.py` into a thin orchestrator

**Status:** Drafted 2026-04-16. Not yet in flight.
**Active-plan pointer:** update `docs/active-plan.md` when M1 opens.
**How to resume:** open this file, find the first `- [ ]` milestone, read its "Files touched" + "Tests" sections, start there. The plan is self-contained; do not rely on chat context.

## Context / Why

`src/cosinabox/app.py` is 773 lines and owns too much:

- Config loading (`_load_personality`, `_load_jobs`, `_load_integrations`, frontmatter regex, `.env`)
- Tool construction + auth error collection (`_build_tools`, lines ~125–210)
- Job registration (`_register_jobs` for the 5 scheduled jobs, plus an inline pile for `inbound_email_check`, `crm_email_sync`, `extract_fireflies`, `extract_gmail`, `post_meeting_debrief`, `scheduling_poll_check`, `rela_daily_scan` in `run()` after `send_telegram` exists)
- Telegram output wrapping (`_wire_telegram_output`)
- Chat DM handler + pending-tool TTL sweep + approval granting
- Auth-error alert routing
- `App.run()` master wiring: timezone, memory, tool registry (twice — once before the loop, once after Rela wires back in), scheduler start, PTB handlers, command handlers
- The standalone `is_approval()` function (Plan 4 polish item 7, with its own test surface)

Rate of change: ~4 PRs in the past 2 weeks modified `app.py`; #22 alone changed 143 lines. Every new feature lands here. The CI trio (#24/#25/#26) leaves main green — this is the right window to split.

## Non-goals

- No runtime behaviour changes. The refactor is structural only. `App().run()` must produce the same jobs, handlers, tools, and Telegram side effects in the same order.
- No renaming of public functions/classes beyond what the split strictly requires. `App`, `App.run`, and `is_approval` keep their names and import paths (`from cosinabox import App`, `from cosinabox.app import is_approval`).
- No new features, no new config keys, no new jobs, no new tools.
- No changes to `src/cosinabox/templates/user-repo/main.py` (it does `from cosinabox import App`; that import must keep working).
- No changes to the Telegram handler's async shape or the pending-tool TTL logic (just move them).
- No dependency-injection rewrite or class-hierarchy change. Keep the "collect data, then wire" ordering.
- No attempt to collapse the "build tool registry twice" pattern (pre-Rela, then post-Rela). That's a real ordering constraint; leave it alone.
- No attempt to move `is_approval` out of `app.py`'s importable surface. A test pins `from cosinabox.app import is_approval`; preserve it.

## Current state — what `app.py` owns today

Inventory (with approximate line ranges, for the implementer to grep against):

| Responsibility | Where in `app.py` | Shared state / coupling |
|---|---|---|
| `_FRONTMATTER_RE`, `_APPROVAL_PHRASES`, `is_approval` | ~25–70 | `is_approval` is imported by `tests/unit/test_is_approval.py` |
| `App.__init__` (stores `config_dir`) | ~85–90 | — |
| `_load_personality`, `_load_jobs`, `_load_integrations` | ~90–125 | Read-only from disk; pure |
| `_build_tools(integrations)` → `(tools, {}, errors)` | ~125–210 | Imports tool classes lazily; returns `auth_errors` list consumed later by `send_telegram` alert block |
| `_register_jobs(scheduler, jobs_config, *, gmail, calendar, loop, personality, name, stakeholders)` (the "5 core jobs") | ~215–290 | Mutates scheduler |
| `_wire_telegram_output(scheduler, send_fn)` | ~295–325 | Patches `registered_job.run` for every job; must run after ALL jobs are registered |
| `App.run()` master orchestrator | ~325–773 | Everything below |
| Env-var validation (`TELEGRAM_*`, `ANTHROPIC_API_KEY`) | ~340–360 | Inside `run()` |
| Timezone setup (called twice — once after config load, once before scheduler) | ~345, ~460 | `cosinabox.timezone.set_timezone` |
| Memory + memory_client construction | ~375–385 | `self.config_dir / ".cosinabox" / "memory.db"` |
| `scheduling_ctx` construction (lazy, opt-in) | ~390–410 | Shared between tool registry, scheduling_poll_check job, bot callback handler; `cost_tracker` and `bot` are patched in AFTER `loop` and `tg_app` exist |
| Tool registry built once (pre-Rela) | ~410–420 | `build_tool_registry(tool_instances, timezone, scheduling_ctx)` |
| `AgentLoop` + `CostTracker` construction | ~420–445 | — |
| Rela agent (optional) | ~445–465 | Built after loop; requires `memory_client`; its registration retro-patches `loop.tools` + `loop.tool_definitions` |
| Tool registry rebuilt (post-Rela) | ~465–480 | Second `build_tool_registry` call, then `loop.tools = …`, `loop.tool_definitions = …` |
| Scheduler construction + `_register_jobs` call | ~485–510 | |
| Telegram `send_telegram(text)` closure | ~510–525 | Captures `bot_token`, `chat_id`; used by auth-error alert AND by the 7 extra jobs AND by `_wire_telegram_output` |
| Auth-error alert via `send_telegram` | ~525–540 | Consumes `auth_errors` from `_build_tools` |
| Extra jobs registration (7 jobs needing `send_telegram`, memory, memory_client, stakeholders, rela, scheduling_ctx, etc.) | ~540–620 | |
| `_wire_telegram_output(scheduler, send_telegram)` call | ~625 | Must run after ALL jobs including the extras |
| `scheduler.start()` | ~630 | |
| PTB setup: pending-tool dict + lock + TTL sweep + `handle_message` | ~635–710 | `_pending_tools`, `_pending_tools_lock`, `_PENDING_TOOL_TTL_S = 300`; calls `is_approval`; invokes `grant_temporary_approval` |
| Scheduling callback handler + `SyncSchedulingBotAdapter` (opt-in) | ~710–730 | Patches `scheduling_ctx["coordinator_ctx"]["bot"]` |
| Bot command handlers (`/help`, `/start`, `/status`, `/cost`, `/brief`, `/analytics`) | ~730–770 | |
| `tg_app.run_polling(...)` | ~773 | Blocks forever |

### External callers (must not break)

- `src/cosinabox/__init__.py`: `from cosinabox.app import App` and `__all__ = ["App", ...]`.
- `src/cosinabox/templates/user-repo/main.py`: `from cosinabox import App; App().run()`. User repos already in the wild do the same.
- `tests/unit/test_auth_failure_visibility.py`: `from cosinabox.app import App`, then `app = App(...); app._build_tools(integrations)`.
- `tests/unit/test_is_approval.py`: `from cosinabox.app import is_approval`.
- `tests/stress/test_plan4c_stress.py`: `import cosinabox.app` (smoke).
- Doc/comment references in `src/cosinabox/tools/registry.py` and `src/cosinabox/bot/commands.py` mention `App._build_tools` / `App.run` but do not import them.

**Conclusion:** the public surface to preserve is exactly `cosinabox.App`, `cosinabox.app.App`, `cosinabox.app.is_approval`, and — for the existing test — `App._build_tools(integrations) -> (tools, _, errors)` with that exact return shape.

## Target state — module layout

Create a package `src/cosinabox/app/` that replaces the single-file module. Python will pick the package over the file as long as we delete `app.py` in the same commit we add `app/__init__.py`. (Alternative: keep `app.py` as the orchestrator and put helpers in `src/cosinabox/_app/`. We choose the package form because the retro explicitly called for it and it better signals the split. The package's `__init__.py` re-exports everything the current `app.py` exposed so external imports keep working.)

```
src/cosinabox/app/
├── __init__.py        # Re-exports: App, is_approval, _FRONTMATTER_RE (defensive).
│                      # No logic. ~10 lines.
├── config.py          # _load_personality, _load_jobs, _load_integrations,
│                      # _FRONTMATTER_RE. Pure functions taking `config_dir: Path`.
│                      # No App dependency. ~70 lines.
├── tools.py           # build_tools(integrations) -> (tools, {}, errors).
│                      # Exactly the current _build_tools body, lifted to a
│                      # module function. App._build_tools becomes a thin
│                      # delegating method to preserve the test's call site.
│                      # ~90 lines.
├── jobs.py            # register_core_jobs(scheduler, jobs_config, *, ...) and
│                      # register_telegram_jobs(scheduler, jobs_config, *, ...)
│                      # Two functions because the first set needs no
│                      # send_telegram and runs BEFORE it exists; the second
│                      # set needs it and runs AFTER. Preserves current order.
│                      # ~200 lines.
├── alerts.py          # make_send_telegram(bot_token, chat_id) -> send_fn
│                      # and send_auth_error_alert(send_fn, auth_errors).
│                      # Plus _wire_telegram_output(scheduler, send_fn) moves here.
│                      # ~50 lines.
├── chat.py            # Pending-tool TTL dict + lock + sweep + handle_message
│                      # factory. Exposes build_dm_handler(loop, chat_id) -> async fn
│                      # and the is_approval constant/function (re-exported from
│                      # __init__.py to preserve test import).
│                      # ~100 lines.
└── _core.py           # The App class itself + run() orchestrator, importing
                       # from the modules above. ~180 lines, down from 773.
```

Why this split (and not the initial `config/tools/jobs/alerts` hypothesis verbatim):

- **`chat.py` is added** because the DM handler + TTL sweep + `is_approval` is ~80 lines of stateful logic that has its own test file and is independently reviewable. Leaving it inside `_core.py` would leave the orchestrator at ~260 lines.
- **`alerts.py` absorbs `_wire_telegram_output`** in addition to the auth-error alert. Both are "Telegram side-effects wrapping", and both must be ordered around job registration. Co-locating them makes the ordering contract explicit in one file.
- **`jobs.py` exports two functions**, not one. Merging them would force `send_telegram` to exist earlier, which it can't without restructuring `run()` more than we want.
- **`_core.py` (underscore prefix)** signals "internal; import `App` from the package root." Users do `from cosinabox import App` and see nothing else.

### Public-surface re-exports (`src/cosinabox/app/__init__.py`)

```python
# app/__init__.py  (sketch — not code to write now)
from cosinabox.app._core import App
from cosinabox.app.chat import is_approval
from cosinabox.app.config import _FRONTMATTER_RE  # defensive; not known to be imported externally

__all__ = ["App", "is_approval"]
```

This keeps `from cosinabox.app import App`, `from cosinabox.app import is_approval`, and `import cosinabox.app` all green. `from cosinabox import App` already works via the existing `src/cosinabox/__init__.py`.

## Milestones

Each milestone is one PR, independently reviewable, keeps all 627 tests green, and has a one-line entry in `docs/active-plan.md` when it opens.

---

### - [ ] M1: Introduce `app/` package skeleton with no behaviour change (NOOP cutover)

**Goal:** flip `app.py` into `app/` package without moving any logic. The package's `_core.py` is a verbatim copy of the current `app.py`. Prove the import surface is preserved.

**Files touched:**
- Delete: `src/cosinabox/app.py`
- Add: `src/cosinabox/app/__init__.py` (re-exports `App`, `is_approval`)
- Add: `src/cosinabox/app/_core.py` (byte-for-byte content of old `app.py`, minus the `is_approval` function — which moves to `chat.py` in this same PR so tests keep importing `from cosinabox.app import is_approval` via `__init__.py`)
- Add: `src/cosinabox/app/chat.py` (contains ONLY `_APPROVAL_PHRASES` and `is_approval`; nothing else moves yet)

**Tests run:** full suite (`pytest tests/` — 627 tests), plus smoke: `python -c "from cosinabox import App; from cosinabox.app import App, is_approval; import cosinabox.app"`

**Risk / rollback:** if any test fails on an import path, the fix is to add a re-export to `app/__init__.py`. Rollback is `git revert`; no data or config touched. The `tests/stress/test_plan4c_stress.py::test_cosinabox_app_import_does_not_crash` is the canary here.

**PR title:** `refactor(app): package skeleton, no behaviour change (Plan app-refactor, M1)`
**PR exit criteria:** CI green, no other file in the repo modified.

**Estimate:** 30 min.

---

### - [ ] M2: Extract `config.py`

**Goal:** move `_load_personality`, `_load_jobs`, `_load_integrations`, and `_FRONTMATTER_RE` out. `App` methods become thin delegators.

**Files touched:**
- Add: `src/cosinabox/app/config.py` with module-level `load_personality(config_dir) -> (body, name, tz)`, `load_jobs(config_dir) -> dict`, `load_integrations(config_dir) -> dict`, `_FRONTMATTER_RE`.
- Modify: `src/cosinabox/app/_core.py` — `App._load_personality` etc. call into `config` module.

**Tests run:** full suite. No test directly imports the private loaders; the delegators preserve the method interface.

**Risk / rollback:** frontmatter regex semantics are load-bearing (quirky `\n` handling). The port must be byte-identical. If a test in `test_is_approval` or template tests starts failing, revert and diff the regex literal.

**PR title:** `refactor(app): extract config loading (M2)`

**Estimate:** 30 min.

---

### - [ ] M3: Extract `tools.py`

**Goal:** move `_build_tools` logic to `app/tools.py` as a module function `build_tools(integrations) -> (tools, {}, errors)`. `App._build_tools` becomes a one-line delegator — **kept because `tests/unit/test_auth_failure_visibility.py` calls `app._build_tools(integrations)` directly on an instance.** Do NOT change the return shape (the `{}` middle element).

**Files touched:**
- Add: `src/cosinabox/app/tools.py`
- Modify: `src/cosinabox/app/_core.py` — `_build_tools` becomes `return build_tools(integrations)`.

**Tests run:** full suite, with special attention to the 5 tests in `test_auth_failure_visibility.py` (assert error strings for Google/Fireflies/Serper/Attio init failures; the error message text is load-bearing — keep exact strings including "Run `cosinabox auth google` to refresh tokens").

**Risk / rollback:** the error message strings are asserted with `in` substrings in tests — exact copy is required. Lazy imports inside each `if integrations.get(...)` block must remain lazy (they gate on optional deps).

**PR title:** `refactor(app): extract tool construction (M3)`

**Estimate:** 45 min.

---

### - [ ] M4: Extract `jobs.py` (both core jobs and telegram-dependent jobs)

**Goal:** move `_register_jobs` (5 core jobs) and the inline extras (7 jobs that need `send_telegram`) to `app/jobs.py` as `register_core_jobs(...)` and `register_telegram_jobs(...)`. Call sites in `_core.py:run()` become two function calls instead of a class method + a 90-line inline block.

**Files touched:**
- Add: `src/cosinabox/app/jobs.py`
- Modify: `src/cosinabox/app/_core.py`

**Tests run:** full suite. The 5 per-job tests (`test_jobs_morning_briefing.py`, `test_jobs_evening_wrap.py`, `test_jobs_pre_meeting_prep.py`, `test_jobs_weekly_review.py`, `test_jobs_followup_reminder.py`) instantiate jobs directly and don't exercise the registration path, so they should keep passing. Integration tests in `tests/integration/` do NOT run `App.run()` end-to-end (verified during exploration), so no integration-level risk here.

**Risk / rollback:** the scheduling_ctx coupling is subtle — `cost_tracker` and `bot` are patched into `scheduling_ctx["coordinator_ctx"]` AFTER the tool registry is first built. The job registration for `scheduling_poll_check` reads `scheduling_ctx["coordinator_ctx"]["cost_tracker"]` at registration time (not run time), so the patching order must be preserved: build loop → patch cost_tracker into scheduling_ctx → build tool registry again → register scheduling_poll_check. If the refactor reorders these, `cost_tracker` will be `None` at job construction. Mitigation: port the ordering comments verbatim.

**PR title:** `refactor(app): extract job registration (M4)`

**Estimate:** 2 hr (largest PR — the 7-job inline block is the densest code in the file).

---

### - [ ] M5: Extract `alerts.py` (send_telegram factory, auth-error alert, _wire_telegram_output)

**Goal:** move the `send_telegram` closure factory, the auth-error alert block, and `_wire_telegram_output` to `app/alerts.py`.

**Files touched:**
- Add: `src/cosinabox/app/alerts.py` with `make_send_telegram(bot_token, chat_id) -> Callable[[str], None]`, `send_auth_error_alert(send_fn, errors)`, and `wire_telegram_output(scheduler, send_fn)`.
- Modify: `src/cosinabox/app/_core.py`

**Tests run:** full suite. `test_auth_failure_visibility.py::test_auth_errors_routed_through_send_telegram` is the key test — it reconstructs the alert block manually, so if we change the alert format/prefix (`"[cosinabox startup] Integration auth issues detected:"`), that test breaks. Keep the string exact.

**Risk / rollback:** `_wire_telegram_output` mutates `registered_job.run` in place and depends on calling AFTER all jobs are registered. Keep the call order in `run()`: core jobs → telegram-dep jobs → `wire_telegram_output`. The NO_OP tuple `("no upcoming", "no events", "no meetings", "(no ")` is also load-bearing and must port exactly.

**PR title:** `refactor(app): extract alert + telegram wiring (M5)`

**Estimate:** 45 min.

---

### - [ ] M6: Extract `chat.py` (DM handler + pending-tool TTL)

**Goal:** move the DM handler, `_pending_tools` dict, lock, TTL sweep, and `handle_message` async function to `app/chat.py`. Expose a factory `build_dm_handler(loop, chat_id) -> async handler`. Note `is_approval` already moved here in M1.

**Files touched:**
- Modify: `src/cosinabox/app/chat.py` (add handler factory alongside the already-moved `is_approval`)
- Modify: `src/cosinabox/app/_core.py`

**Tests run:** full suite. `test_is_approval.py` imports `is_approval` via `from cosinabox.app import is_approval` — still green via `app/__init__.py` re-export.

**Risk / rollback:** the `_pending_tools_lock` is a `threading.Lock`, not `asyncio.Lock`, deliberately (the PTB handler runs on the async loop, but scheduling outreach runs in sync worker threads — see the inline comment). Port the comment AND the lock type verbatim. The 300-second TTL constant is also load-bearing.

**PR title:** `refactor(app): extract DM handler (M6)`

**Estimate:** 1 hr.

---

### - [ ] M7: Thin `_core.py` — final cleanup + update comments

**Goal:** with all modules extracted, `_core.py` should be ~150–180 lines: just `App.__init__`, `App.run()` as straight-line wiring, and the three thin delegators (`_build_tools`, `_load_personality`, etc. kept for the test + any subclasser). Update the 3 docstring/comment references to `App._build_tools` / `App.run` in `tools/registry.py`, `bot/commands.py`, and `app/_core.py` itself to point at the new module paths.

**Files touched:**
- Modify: `src/cosinabox/app/_core.py`, `src/cosinabox/tools/registry.py` (comment only), `src/cosinabox/bot/commands.py` (comment only), `CLAUDE.md` (project-structure diagram now shows `app/` package)

**Tests run:** full suite + manual `grep -rn 'App._build_tools\|App.run' src/ docs/` to confirm no stale references.

**Risk / rollback:** none; this is a comment-only + final inlining pass.

**PR title:** `refactor(app): thin orchestrator, close plan (M7)`

**Estimate:** 30 min.

---

### - [ ] M8: Retro

Write `docs/retros/2026-04-16-app-refactor-retro.md` within 24 hours of M7 merging, per commitment 3. Capture: actual vs estimate per milestone, any subtle coupling that surprised us (my bet: the scheduling_ctx patching order), whether the package split paid off for the next feature.

## Test impact

- **No test file needs to move or be renamed.** Every existing test keeps the same import path because `app/__init__.py` re-exports `App` and `is_approval`.
- **No test needs to change imports.** `from cosinabox.app import App` resolves to the package; `from cosinabox.app import is_approval` resolves via re-export.
- **One test is implicitly a regression oracle:** `tests/stress/test_plan4c_stress.py::test_cosinabox_app_import_does_not_crash` runs `import cosinabox.app` — this will catch any circular import introduced by the split.
- **Error-message-exactness tests to watch:** `test_auth_failure_visibility.py` asserts substring matches on 4 init-failure strings and on the `"[cosinabox startup] Integration auth issues detected:"` prefix. Port the strings verbatim.
- No new tests are added in this refactor. The 627-test count should be unchanged after M7. (If, during review, we identify a behaviour that was implicitly tested only via `App.run()`, we flag it in the retro — do not add tests inside refactor PRs.)

## Risks

1. **scheduling_ctx patching order** (M4). The `cost_tracker` / `bot` fields are mutated after construction and before downstream consumers read them. Any reordering in `run()` that moves `scheduling_poll_check` registration before the `loop.cost` patch will silently pass a `None` cost tracker into the job. Mitigation: port `run()` body as straight-line code; do not refactor ordering inside M4.
2. **Tool registry built twice** (also M4). The pre-Rela and post-Rela `build_tool_registry` calls look like duplication but aren't — Rela's `rela_query` tool depends on the `AgentLoop`, which depends on the first registry. Leave both calls; add a one-line comment pointing at this plan.
3. **`_wire_telegram_output` mutates in place** (M5). Mutates `scheduler._jobs[jname].run`. If moved to run BEFORE all jobs are registered, late-registered jobs won't be wrapped. Keep it last.
4. **Lazy imports inside `_build_tools`** (M3) are deliberate — optional deps may not be installed. If the extraction accidentally hoists them to module-level, a user with `integrations.yaml` disabling Fireflies will hit an `ImportError` at `import cosinabox.app`. Regression test: `test_cosinabox_app_import_does_not_crash`.
5. **`App._build_tools` test call** (M3) — the method signature `_build_tools(self, integrations)` and return tuple `(tools, {}, errors)` are asserted by the test suite. The middle `{}` is currently unused but present; preserve it (do not "clean it up" in this refactor).
6. **Frontmatter regex** (M2) — `_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)", re.DOTALL)`. Copy-paste, don't retype. Any whitespace tweak breaks personality.md parsing silently (falls through to "no frontmatter" path).
7. **`threading.Lock` vs `asyncio.Lock`** in `chat.py` (M6) — the sync lock is deliberate because scheduling outreach runs on sync worker threads. Do not "modernize" to `asyncio.Lock`.
8. **Package-vs-file shadowing** (M1) — deleting `app.py` and adding `app/` in the same commit is required. Having both briefly (e.g., a half-applied commit) produces undefined import behaviour. Enforce via a single commit at M1.
9. **Template user-repo** — `src/cosinabox/templates/user-repo/main.py` does `from cosinabox import App`. Already covered by re-export, but confirm manually at M1 with the smoke-import and at M7 before closing.

## Open questions

1. Should `is_approval` move to `cosinabox.agent.policy` eventually (it's adjacent to `grant_temporary_approval`)? Not in this plan — it's touched by a named test and would require a test-import change. Flag in retro.
2. Should the two-phase job registration (`register_core_jobs` + `register_telegram_jobs`) be collapsed by moving `send_telegram` construction earlier? Probably yes, but it's a behaviour-adjacent change and out of scope here.
3. Does CLAUDE.md's project-structure diagram need updating in M7, or is that a separate docs PR? Proposal: update in M7 because it's one-line.
4. The plan lives at `docs/plans/` per the initial preference; the repo's CLAUDE.md references `docs/superpowers/plans/` (which doesn't exist yet). Should we create `docs/superpowers/plans/` and move this plan there for consistency? Ask before M1.
