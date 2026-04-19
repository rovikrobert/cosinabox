# Plan: Port `commitments` + `auto_resolve` from cos-agent to cosinabox

**Status:** Not started.
**Source:** `~/code/cos-agent/src/commitments.py` (635 lines), `~/code/cos-agent/src/commitments_db.py` (80 lines), `~/code/cos-agent/src/auto_resolve.py` (369 lines).
**Target:** new `src/cosinabox/commitments/` package + wiring into 4 briefing jobs.
**Cutover tag:** **port** (from the cutover inventory — row 1 after agent_failover).
**How to resume:** open this file, find the first `- [ ]` milestone, read its "Files touched" + "Tests" sections, start there. Self-contained; do not rely on chat context.

## Context / Why

Today cosinabox has no authoritative record of "open" work. Four briefing jobs suffer downstream symptoms of that gap:

| Job | Symptom | Fixed by this port |
|---|---|---|
| `evening_wrap` | CARRY-OVER / TOMORROW sections dropped in PR #56 because they had no grounded source | Re-enable with `verify_all_open_commitments` grounding |
| `weekly_review` | MISSES / NEXT WEEK sections dropped in PR #56 for same reason | Re-enable |
| `morning_briefing` | PRIORITIES section is softly ungrounded | Replace with commitment-driven priorities |
| `follow-up` logic | Can't auto-resolve "did X get done" — user has to manually edit `last_contact` | `auto_resolve` checks Gmail + Drive |

cos-agent solves this with:
1. A **commitments table** (titles, owner, priority, deadline, status, source).
2. A **verifier** that walks open commitments and tags each with a verdict:
   - `VERIFIED_DONE` — strong evidence (matching sent email, doc in Drive).
   - `LIKELY_DONE` — weak evidence (mentioned in sent mail).
   - `NO_EVIDENCE` — nothing found in the lookback window.
3. Briefings inject the verifier output and carry an absolute rule: **only `NO_EVIDENCE` items can appear as carry-over / misses / priorities.**

This is the biggest remaining dependency on cos-agent. Porting unblocks re-enabling the dropped sections, removes the "just hallucinate from memory" failure mode, and is a prerequisite for shipping the Chief of Staff v1 experience promised by the spec.

## Non-goals

- **No Postgres dependency.** cos-agent uses `asyncpg`; cosinabox is SQLite-first. Port the schema onto the existing `Memory` SQLite layer; Postgres can be a later runtime option via the same interface.
- **No async.** cos-agent is `async` throughout; cosinabox's job/agent layer is sync. Port as sync. Async wrapper can come later if needed.
- **No auto-create from chat.** cos-agent auto-creates commitments from conversations via tool calls. That needs prompt engineering + tool permission policy — separate PR after the DB layer lands.
- **No manual-closures backfill from production.** cos-agent maintains `manual_closures` for "user said: not doing this." Port the table + verb but don't migrate data.
- **No Drive search in v1.** `auto_resolve` searches Gmail + Drive; port Gmail only first. Drive adds another OAuth scope + an extra integration. File a follow-up for Drive.
- **No Attio bi-directional sync.** cos-agent has deep Attio integration for commitments; cosinabox's `CrmEmailSyncJob` is read-only. Stay read-only.

## Milestones

### M1 — SQLite commitments schema + CRUD helpers

**Files touched:**
- `src/cosinabox/memory/__init__.py` (or `memory/_schema.py` — wherever existing DDL lives) — add 2 tables.
- `src/cosinabox/commitments/__init__.py` (new) — CRUD helpers.
- `src/cosinabox/commitments/models.py` (new) — `CommitmentStatus` enum, `Commitment` dataclass.

**Tests:** `tests/unit/test_commitments_crud.py` (new).

- [ ] Schema: translate the Postgres DDL to SQLite. Map `SERIAL` → `INTEGER PRIMARY KEY AUTOINCREMENT`, `TIMESTAMPTZ` → `TEXT` (ISO 8601), `CHECK` constraints → preserved.
  ```sql
  CREATE TABLE IF NOT EXISTS commitments (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      description TEXT,
      owner TEXT NOT NULL DEFAULT 'user',
      status TEXT NOT NULL DEFAULT 'open'
          CHECK (status IN ('open', 'in_progress', 'done', 'blocked', 'cancelled')),
      priority INTEGER NOT NULL DEFAULT 3
          CHECK (priority BETWEEN 1 AND 5),
      deadline TEXT,
      source TEXT NOT NULL DEFAULT 'manual'
          CHECK (source IN ('chat', 'email', 'meeting', 'manual')),
      source_ref TEXT,
      stakeholder TEXT,
      workstream TEXT,
      last_verdict TEXT,
      last_verdict_at TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX IF NOT EXISTS idx_commitments_status ON commitments(status);
  CREATE INDEX IF NOT EXISTS idx_commitments_deadline ON commitments(deadline);

  CREATE TABLE IF NOT EXISTS manual_closures (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      commitment_id INTEGER NOT NULL REFERENCES commitments(id),
      verb TEXT NOT NULL CHECK (verb IN ('close', 'dismiss')),
      reason TEXT,
      closed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      closed_by TEXT NOT NULL DEFAULT 'user'
  );
  ```
- [ ] Port `CommitmentStatus` enum + the three exception classes verbatim.
- [ ] Port CRUD as sync: `create_commitment`, `list_commitments`, `get_commitment`, `update_commitment`, `close_commitment`, `reopen_commitment`, `dismiss_commitment`, `list_recent_closures`.
  - Accept a `Memory` instance (keeps SQLite coupling explicit).
  - Drop the `owner` default of `"rovik"` → use `"user"` (OSS-safe).
- [ ] Tests:
  - Create → list returns it with `status=open`.
  - Update status to `done` → hidden from `list_commitments(status_filter=[open])`.
  - `close_commitment` inserts a `manual_closures` row AND flips status to `done`.
  - `CommitmentNotFound` / `CommitmentAlreadyClosed` raise correctly.
  - Priority/status constraint violations surface as sqlite IntegrityError.

**Estimate:** 3 hours.

### M2 — `auto_resolve` verifier (Gmail only)

**Files touched:**
- `src/cosinabox/commitments/auto_resolve.py` (new).
- `src/cosinabox/defaults.py` — `AUTO_RESOLVE_LOOKBACK_DAYS`, `AUTO_RESOLVE_CONCURRENCY`, `AUTO_RESOLVE_TIMEOUT_PER_ITEM_S`.

**Tests:** `tests/unit/test_commitments_auto_resolve.py` (new).

- [ ] Port `_extract_keywords`, `_sanitize_query`, `_STOP_WORDS` verbatim — pure string logic, no async.
- [ ] Port `verify_commitment(commitment, gmail)` as sync:
  - Build keyword list from title + stakeholder first-name.
  - Search `in:sent newer_than:7d <keywords>` via `gmail.search`.
  - If ≥2 matches → `VERIFIED_DONE` with the top sender/subject as evidence.
  - If 1 match → `LIKELY_DONE`.
  - Else → `NO_EVIDENCE`.
  - Drop the Drive search path — mark with `# TODO: Drive search in follow-up`.
- [ ] Port `verify_all_open_commitments(db, gmail, limit=20)`:
  - Use `concurrent.futures.ThreadPoolExecutor` with `AUTO_RESOLVE_CONCURRENCY` workers instead of `asyncio.Semaphore`.
  - Per-item timeout via `future.result(timeout=AUTO_RESOLVE_TIMEOUT_PER_ITEM_S)`.
- [ ] Port `format_for_briefing(verified_list) -> str` verbatim.
- [ ] Tests with mocked Gmail:
  - 0 matches → NO_EVIDENCE.
  - 1 match → LIKELY_DONE.
  - 3 matches → VERIFIED_DONE.
  - Stakeholder first-name is the first search keyword.
  - Gmail exception → NO_EVIDENCE + `_evidence` string `"error: ..."`.
  - Timeout → NO_EVIDENCE + `"verification timed out"`.
  - `format_for_briefing([])` → `""`.
  - Output groups by verdict with the expected section headers cos-agent uses.

**Estimate:** 4 hours.

### M3 — Wire into `evening_wrap` and `weekly_review`

**Files touched:**
- `src/cosinabox/jobs/evening_wrap.py` — add `db` + `gmail` params; prefetch commitment verdicts; re-enable CARRY-OVER section.
- `src/cosinabox/jobs/weekly_review.py` — same, re-enable MISSES + NEXT WEEK.
- `src/cosinabox/app/jobs.py` — pass `memory` to both job constructors.

**Tests:** extend `test_jobs_evening_wrap.py`, `test_jobs_weekly_review.py`.

- [ ] `evening_wrap._prefetch` appends the `format_for_briefing` output after SENT MAIL.
- [ ] `evening_wrap.run` prompt: restore CARRY-OVER + TOMORROW sections, but add the cos-agent absolute rules:
  ```
  - If COMMITMENT VERIFICATION shows VERIFIED DONE → NEVER list as carry-over.
  - If COMMITMENT VERIFICATION shows LIKELY DONE → treat as done.
  - Only items in GENUINELY OPEN can be carry-overs.
  ```
- [ ] Remove the "Do NOT produce CARRY-OVER or TOMORROW" rule from PR #56 — grounding is now real.
- [ ] `weekly_review.run` prompt: restore MISSES + NEXT WEEK with same verdict-based rules.
- [ ] Update tests:
  - With an empty commitments table, CARRY-OVER / MISSES sections don't appear (no items to carry).
  - With 1 `NO_EVIDENCE` commitment in prefetch, the prompt contains "GENUINELY OPEN" and the commitment title.
  - With only `VERIFIED_DONE` commitments, CARRY-OVER is empty.
  - Regression: the PR #56 assertion "Do not invent items" still appears.

**Estimate:** 2 hours.

### M4 — Wire into `morning_briefing`

**Files touched:**
- `src/cosinabox/jobs/morning_briefing.py` — inject commitment verdicts into prefetch, update prompt's PRIORITIES section.

**Tests:** extend `test_jobs_morning_briefing.py`.

- [ ] `_prefetch` appends `format_for_briefing` output.
- [ ] Prompt: `PRIORITIES — top 3 items from GENUINELY OPEN, ordered by (deadline, priority). If GENUINELY OPEN is empty, skip the section.`
- [ ] Test: with 3 open commitments, the prompt contains them; with 0, the PRIORITIES instruction is still there but the data block is empty.

**Estimate:** 1 hour.

### M5 — Agent-facing tools

**Files touched:**
- `src/cosinabox/tools/registry.py` — register 4 new tools.
- `src/cosinabox/tools/commitments.py` (new) — wrappers around CRUD.

**Tests:** `tests/unit/test_tool_commitments.py` (new).

- [ ] `commitment_create(title, priority?, deadline?, stakeholder?, source?, workstream?, description?) -> str` — returns `"Created #NN: ..."`.
- [ ] `commitment_list(status?="open", limit?=20) -> str` — formatted bullet list.
- [ ] `commitment_update(id, status?, priority?, deadline?, ...) -> str` — returns diff string.
- [ ] `commitment_close(id, reason?) -> str` + `commitment_dismiss(id, reason?) -> str` — return confirmation.
- [ ] Tool schemas in JSON form, plain-language descriptions, examples in the description per `OSS-user perspective` rule.
- [ ] Policy: all 4 tools default to `ALLOW` (no PII exfiltration; DB-local state only).
- [ ] Tests: happy path per tool, invalid id, closed-then-close raises `CommitmentAlreadyClosed` and the tool surfaces it as an error string (not an exception).

**Estimate:** 3 hours.

### M6 — User-facing docs + CLI

**Files touched:**
- `src/cosinabox/templates/user-repo/docs/agent/editing-config.md` — add a "Commitments" section: how the agent uses them, how to add/close via Claude Code ("remind me to follow up with Sarah by Friday" → tool call).
- `src/cosinabox/templates/user-repo/docs/agent/jobs.md` — note the new behavior of evening/weekly briefings.
- `src/cosinabox/cli/describe.py` — add a "Commitments" section showing counts by status.
- `src/cosinabox/cli/simulate.py` — accept a `--commitments` fixture path for reproducible simulations.

**Tests:** extend `test_cli_describe.py`.

- [ ] `cosinabox describe` shows `Commitments: 3 open, 1 in_progress, 12 done (last 30d)`.
- [ ] Simulate fixture can pre-seed commitments.

**Estimate:** 2 hours.

### M7 — Commit, PR, merge

**Files touched:** none (git only).

- [ ] Commits split per milestone where practical so review stays readable.
- [ ] PR title: `feat(commitments): port tracking + auto-resolve from cos-agent`.
- [ ] PR body: link to this plan + cos-agent source reference + cutover inventory update.
- [ ] `gh pr create ... && gh pr merge --auto --squash`.

**Estimate:** 30 min.

### M8 — Update cutover inventory + retro

**Files touched:**
- `~/code/cos-agent/docs/superpowers/specs/2026-04-17-cosinabox-cutover.md` — flip the `commitments` + `auto_resolve` rows to `ported`.
- `docs/retros/2026-XX-XX-port-commitments.md` (new) — one-page retro.

- [ ] Inventory PR in cos-agent.
- [ ] Retro covers: actual vs estimated hours, surprises, whether the 2-week follow-up (Drive search) should happen.

**Estimate:** 30 min.

## Open questions for kickoff

1. **Schema version bump?** The user-facing yaml schemas don't change; the new tables are in the engine's SQLite, not user config. Proposal: **no bump**. Confirm at M1.
2. **Commitment creation UX.** Expecting users to hand-create via tool calls is friction. Should the interview flow seed a few starter commitments? → Queue for post-port.
3. **Migration of existing deployments.** Adding 2 tables to an already-initialized SQLite should just work on engine upgrade. Sanity-check at M1 with an existing `rovik-keevs` snapshot.

## Total estimate

~16 hours. Bigger than the failover port by 8x — most of the weight is M2 (verifier) and M5 (tools). Realistic to ship across 2–3 sessions.

## Out of scope / follow-ups

- **Drive search.** M2 notes where to hook it in; separate 4-hour PR.
- **Async wrapper.** If APScheduler ever runs jobs on an async loop natively, wrap `verify_all_open_commitments` in `asyncio.to_thread`.
- **Auto-creation from chat/email/meeting.** Explicit source slots exist in the schema; wire them up after the manual flow feels right.
- **Commitment history / audit log.** Currently only `manual_closures` logs closure events. If users want "who changed status when" that's a second audit table.
- **Per-stakeholder rollups.** "What's open for Sarah this quarter?" Add a groupby tool in the follow-up PR.
