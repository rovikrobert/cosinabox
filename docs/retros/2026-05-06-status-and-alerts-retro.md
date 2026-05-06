# Retro: `/status` per-account auth + alert enrichment (Initiative C)

**Plan:** `docs/plans/2026-05-06-status-and-alerts.md`
**Spec:** `docs/specs/2026-05-06-oauth-ux-rework.md`, "Initiative C"
**PR:** #89
**Date:** 2026-05-06

## What shipped

- New `auth_health_status` SQLite table inside `memory.db`. PK on `account_index`. Schema: `(account_index, email, last_status, last_check_at)`. Statuses: `'ok' | 'failed'`; transient errors don't write so prior known state survives network blips.
- `AuthHealthJob.__init__` takes `db_path` + `account_emails`; `run()` upserts a row per credential per tick. Backwards compat: omitting `db_path` skips persistence.
- `/status` appends `OAuth: ✓ rovik@majiq.agency | ✗ rovik@cantina.ai` line when the table has rows. Hidden on fresh deploys (no rows yet).
- Both alert surfaces (`auth_health.py:_FAILURE_TEMPLATE` proactive + `_runtime_alert.py` live failure during job run) now end with `Run: cosinabox auth refresh`. The legacy three-step manual flow is gone from every user-facing string.
- Wired `memory.db` path + Google account emails (read from `integrations.yaml`) through `register_core_jobs` → `AuthHealthJob` and through `build_status_handler` from `app/_core.py`.
- 8 new tests + 2 updated; 994 unit tests green (was 990).

## What was planned vs what shipped

| Milestone | Planned | Actual | Note |
|---|---|---|---|
| M1 — Sign-off | 0 | 0 | Q5–Q9 signed off in chat before code |
| M2 — Persistence module | 30 min | ~15 min | One-table SQLite + UPSERT, no migration concerns |
| M3 — Wire AuthHealthJob | 45 min | ~25 min | Existing tests for `_FAILURE_TEMPLATE` text needed updates — caught at TDD red phase, not later |
| M4 — Update `_runtime_alert.py` | 20 min | ~10 min | One-line template change + new test |
| M5 — `/status` reads + renders | 30 min | ~20 min | Trivial once persistence existed |
| M6 — PR + retro | 15 min | ~10 min | |

**Total:** ~80 min vs ~140 min planned. ~57% of plan. Closer to the original "wrapper plans cost ~50%" calibration that the addendum to PR #86's retro had revised upward to 70%. Why the difference: this initiative didn't wrap an external CLI, so the smoke-test cost (PR #87 stress fix) didn't apply.

## What went well — keep doing

- **Three small, independent surfaces in one PR.** Persistence module / job wiring / alert templates / status handler all touched different files. No cross-contamination, easy review.
- **Transient-error semantic preserved end-to-end.** The in-memory `_health` dict already had "skip-on-transient" logic; the persistence layer mirrored it via the same `continue` path before the write call. No flaky-row regression.
- **`db_path: Path | None = None` on both `AuthHealthJob` and `build_status_handler`.** Backwards-compat safe — existing callers (and ~50 unit tests using them) didn't need to be touched.
- **Two existing tests asserted the legacy alert wording.** TDD caught them at the red phase, not in CI. Updated both in lockstep with the template change.

## What didn't — change next time

- Nothing surfaced. Plan held; estimates over-budgeted; no design pivot needed.

## Estimate calibration update

PR #87's retro addendum claimed wrapper plans cost ~70%. This plan was *not* a wrapper plan (no external-CLI binding) and clocked ~57%. **Refined rule:**
- **Pure-internal initiative** (touching only Python + SQLite): ~50% of plan budget.
- **External-CLI wrapper** (subprocess to `railway` / `gh` / `gcloud`): ~70% of plan budget once you include the inevitable smoke-test stress fix.

Both are well under the original "1 day" per-spec budget for the half-day initiatives.

## Commitment violations

None. Worktree from session start (CLAUDE.md safety rule 1). Plan as source of truth — no drift; no design changes mid-execution.

## New lessons → memory candidates

- None new. The "manual smoke for CLI wrappers is mandatory" lesson from PR #87 already covers the lesson space here.

## Out of scope / follow-ups

- **`/status` showing last-check timestamp** (e.g. `OAuth: ✓ rovik@majiq.agency (5 min ago)`). Stretch goal; the per-account ✓/✗ is the load-bearing info.
- **Schema migration tracking for `auth_health_status`.** Today the schema is `CREATE TABLE IF NOT EXISTS`; if we ever add a column (e.g. `last_error_class`), a proper migration plan ships with that change.
- **Initiative D** (web-based OAuth flow served by the bot itself) — v0.2 territory. Adds HTTP listener attack surface and Railway-API write permissions on the deploy. Defer until A+B+C have stabilised in production for ≥2 weeks.
