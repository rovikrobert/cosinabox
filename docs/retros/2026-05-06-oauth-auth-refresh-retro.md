# Retro: OAuth UX rework — Initiative A (`cosinabox auth refresh`)

**Plan:** `docs/plans/2026-05-06-oauth-auth-refresh.md`
**Spec:** `docs/specs/2026-05-06-oauth-ux-rework.md` (Initiative A only)
**PR:** #86
**Date:** 2026-05-06

## What shipped

- New CLI command `cosinabox auth refresh` collapses the 10-step manual OAuth re-auth flow into one guided run.
- Single-account: auto-selects with a printed notice. Multi-account: numbered picker, or `--account <email>` for non-interactive.
- Pulls `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` from the linked Railway service, runs OAuth consent in-browser via the existing `mint_refresh_token` helper, writes the new refresh token back to `GOOGLE_OAUTH_REFRESH_TOKEN_<N>`, triggers a redeploy, polls deployment status (5-min timeout).
- Three layered Railway environment checks (CLI installed → logged in → service linked) with copy-pasteable fix commands in each error.
- Legacy unsuffixed `GOOGLE_OAUTH_REFRESH_TOKEN` deployments get a one-time migration warning.
- Template `oauth-walkthrough.md` now leads with `cosinabox auth refresh`; manual ten-step flow stays as a fallback for first-time setup, non-Railway deploys, or when the new command itself errors.
- 29 net-new tests covering happy paths, multi-account, and the six concrete failure modes from the 2026-05-06 production session.

## What was planned vs what shipped

| Milestone | Planned | Actual | Note |
|---|---|---|---|
| M1 — Open questions sign-off | 5 min | 5 min | Q1–Q5 signed off in chat before M2. |
| M2 — Extract `mint_refresh_token` | 30 min | ~10 min | Refactor smaller than expected; existing CLI tests stayed green untouched. |
| M3 — Railway adapter | 1 hr | ~25 min | Mocking subprocess at one boundary kept tests trivial. |
| M4 — Orchestrator happy path | 1 hr | ~30 min | Single-account auto-select + slot logic landed in one pass. |
| M5 — Multi-account picker tests | 30 min | ~15 min | Implementation from M4 already covered the paths; only tests added. |
| M6 — Six failure-mode tests | 1 hr | ~30 min | All tests passed first try after M4's impl. Added two bonus failure tests (legacy warning, missing creds). |
| M7 — Template doc update | 30 min | ~10 min | Surgical edit; smoke tested via `cosinabox init`. |
| M8 — Manual smoke against rovik-keevs | 30 min | **DEFERRED** | Interactive (browser consent + Telegram alert wait). Surfaced to maintainer; verify post-merge. |
| M9 — PR + retro | 15 min | ~15 min | Auto-merge + retro draft. |

**Total wall clock for M2–M7 + M9:** ~2.5 hr (vs ~5 hr estimated). Estimates were 2x too pessimistic across the board.

## What went well — keep doing

- **Open-questions checkpoint as M1.** Five concrete recommendations sent before any code, with tradeoffs surfaced (especially Q4 where I picked the simpler shape over the spec's literal log-tailing). Maintainer signed off in one line. Saved an entire mid-implementation rework cycle.
- **Mocking at the adapter boundary.** Patching `cosinabox.cli.auth_refresh._railway.foo` instead of `subprocess.run` everywhere kept the orchestrator tests focused on orchestration, not on shell mechanics. The adapter has its own subprocess-mocked tests.
- **TDD per task.** Every task wrote the failing test first, watched it fail, then implemented. Caught zero regressions; full unit suite stayed green at every commit.
- **Surgical scope.** One refactor (extract helper), one new module (orchestrator), one new adapter, one doc edit. No drive-by refactors. The diff is readable end-to-end.

## What didn't — change next time

- **Estimates were 2x too high.** Future plans for "wrap an existing flow" scoped work should plan ~50% of what this plan budgeted. Calibration data: when the helper is already extractable and the adapter is thin, ~25 min/milestone is realistic.
- **The plan didn't catch the `GOOGLE_OAUTH_REFRESH_TOKEN_<N>` legacy fallback** in `tools/google/auth.py:62-95` until I read the code during implementation. I surfaced it as bonus Q5. Lesson: when a plan touches an existing code path, do a 5-min code read of the load-bearing function before writing the plan, not after sign-off.

## Estimate calibration

The three biggest overshoots — all in the *opposite* direction (under, not over):

| Task | Estimate | Actual | Ratio |
|---|---|---|---|
| M3 Railway adapter | 60 min | 25 min | 0.42x |
| M5 picker tests | 30 min | 15 min | 0.50x |
| M6 failure-mode tests | 60 min | 30 min | 0.50x |

**Why under:** The refactor in M2 made `mint_refresh_token` callable directly. Once the adapter and helper landed, the orchestrator was straight-line code with no surprises.

## Commitment violations

None observed during implementation. Worktree set up at session start (CLAUDE.md safety rule 1). Plan was source of truth; I did not deviate from M2–M7's specified files. Pre-commit hooks ran on every commit (ruff format reformatted three files; I re-staged and committed).

## New lessons → memory candidates

- **For "wrapper-style" plans (commands that orchestrate existing primitives), default estimates to 50% of TDD-from-scratch work.** Once the primitives exist, glue code is faster than fresh code. Worth a feedback memory if the pattern repeats.

## Out of scope / follow-ups

- **M8 manual smoke.** Maintainer to run `cosinabox auth refresh --account <dead-account>` against rovik-keevs and verify end-to-end. If anything is awkward, file an issue against this PR's change.
- **Initiative B** (`cosinabox doctor` actively probes refresh tokens) — separate plan.
- **Initiative C** (`/status` per-account auth + alert message enrichment) — separate plan after B.
- **Initiative D** (web-based OAuth flow served by the bot) — v0.2 territory.
- **AWS / Fly deploy targets** — sibling adapter modules; introduce when first non-Railway user surfaces.
- **`cosinabox auth refresh` exposed as a Telegram bot command** (`/refresh-auth`) — adjacent to Initiative D.

## Process

Plan → 9 milestones, TDD per task, single PR with auto-merge. Five sign-off questions surfaced before code. No drift; no design changes mid-execution. Retro filed within 30 min of merge.

---

## Addendum (same day, after stress test) — six bugs that PR #87 fixed

**M8 manual smoke was deferred in PR #86. That was wrong.** Within an hour of the merge, a stress test against the real `railway` CLI 4.30.2 surfaced six bugs — two of them critical. Fixed in PR #87.

| # | Severity | Bug | Why M8 would have caught it |
|---|---|---|---|
| S1 | Critical | `railway status --json` schema is `{name, services.edges[].node.name}` — not `{projectName, serviceName}`. Confirmation line always rendered `(unknown project) (unknown service)`. | The first thing the user sees after `--yes` |
| S2 | Critical | `wait_for_deployment` polls `latestDeployment.status` which doesn't exist in railway 4.x output → default path always reports successful redeploys as 5-min timeouts | Default-path failure on every real run |
| S3 | High | Refresh token went through argv (`--set "K=V"`), exposing it via `ps -ef` | Token-in-process-listing leak |
| S4 | High | `set_variable` error string echoed `res.stdout`/`res.stderr` — Railway can echo the value back on validation failure | Token in user-facing exception string |
| S5 | Medium | Orchestrator caught typed exceptions but not `RuntimeError` from `mint_refresh_token` (missing `[google]` extra) → traceback to user | First-time setup with stale venv |
| S6 | Medium | Malformed `integrations.yaml` raised raw YAML traceback | Any typo in config |

**The 5-minute probe that would have surfaced S1+S2:** `railway status --json | python -c 'import json,sys; print(list(json.load(sys.stdin).keys()))'`. That's the entire test. The maintainer's machine had `railway` installed; I didn't run it.

### What this changes for future plans

- **Manual-smoke milestones are non-negotiable when a plan wraps an external CLI.** Do not defer them, even if the diff "feels small" or all unit tests are mocked. Mocked tests verify orchestration; only the real binary verifies schema. New feedback memory candidate.
- **Adapter modules should pin the real schema in a comment or a fixture.** The new `_railway.py` docstrings now spell out the exact railway 4.30.2 shape. Drift is detectable.
- **Default paths must be exercised, not just the bypass flags.** I had thorough `--no-wait` tests but the wait path itself was broken. Tests that mock `wait_for_deployment.return_value=True` told me nothing about whether the real function works.

### Updated estimate calibration

The "M2–M7 took ~50% of plan budget" data point above was misleading: it counted *test-passing* time, not *correct* time. The real Initiative A cost was Plan + PR #86 (~2.5 hr) + PR #87 stress fixes (~1 hr) = ~3.5 hr against the 5 hr budget. Closer to 70% of plan, not 50%. The deferred M8 was hidden technical debt that came due immediately.

---

## Addendum 2 (same day, M8 finally ran) — one race, one diagnostic gap (PR #90)

The maintainer ran the real `cosinabox auth refresh` against `rovik-keevs` after PR #88 merged. The flow ran cleanly through:

- ✅ Project/service detection (`Detected Railway: project=rovik-keevs service=rovik-keevs` — confirms PR #87's S1+S2 schema fix against the real CLI).
- ✅ Multi-account picker rendered correctly with both emails.
- ✅ Confirmation prompt + browser consent.
- ✅ Token written to `GOOGLE_OAUTH_REFRESH_TOKEN_2` (correct slot for account #2; no leak in stdout).

Then **`railway redeploy --yes` exited 1**: "Could not trigger redeploy (railway CLI exit 1). Run `railway logs` to inspect, then retry."

### The race

Railway's `variable set` triggers a deploy automatically by default. Our flow was:
1. `railway variable set GOOGLE_OAUTH_REFRESH_TOKEN_2 --stdin` → Railway queued a deploy
2. Our code immediately ran `railway redeploy --yes` → exit 1, "deploy already in progress"
3. Maintainer ran `railway redeploy --yes` manually a few seconds later → worked

The token write succeeded, so the flow's *outcome* was fine. But the failure surface was visible to the user, and the second issue made it five minutes of debugging.

### The diagnostic gap

PR #87 stripped captured `stdout`/`stderr` from `RailwayError` messages to prevent token leaks (S4). I applied that hardening to **both** `set_variable` (where the leak risk is real) and `redeploy` (where there's no secret in the invocation). Result: Railway's actual "deploy already in progress" message was hidden behind the generic "railway CLI exit 1." Differential leak avoidance is the right shape: hide output from `set_variable` (carries secrets), surface it from `redeploy` (carries none).

### PR #90 fixes

1. `set_variable` passes `--skip-deploys` so it doesn't kick off its own deploy. The orchestrator's explicit `redeploy()` is the only deploy trigger.
2. `redeploy` failures fold the captured stderr/stdout into the user-facing error.

Both have new unit tests. Real-binary M8 already ran (that's where the bug was found); future invocations against any Railway deploy avoid the race.

### What this changes (third confirmation of the rule)

- **PR #87** (post-merge stress test): six bugs in two minutes of manual smoke. Validated the rule.
- **PR #88** (M5b real-Google API smoke): passed clean. Validated the rule by virtue of *not* finding bugs — discipline working as intended.
- **PR #90** (M8 against real Railway, finally): one race + one diagnostic gap. Validated the rule again.

The rule from `feedback_cli_wrapper_smoke_test.md` is now backed by three concrete data points across three PRs in one session. **It works.**

