# Retro: `cosinabox doctor` probes refresh tokens (Initiative B)

**Plan:** `docs/plans/2026-05-06-doctor-oauth-probe.md`
**Spec:** `docs/specs/2026-05-06-oauth-ux-rework.md`, "Initiative B"
**PR:** #88
**Date:** 2026-05-06

## What shipped

- New `OAuthRefreshLiveCheck` in `src/cosinabox/doctor/checks.py`. Loops `build_all_credentials()`, attempts `cred.refresh(Request())` per account, reports per-account result.
  - Healthy → `pass` ("All N Google account(s) refreshed cleanly.").
  - `RefreshError` → `fail` ("Refresh failed for: <email>. Run: cosinabox auth refresh").
  - `TransportError` / generic exception → `warn` ("Transient network error...; retry in a moment.").
  - `GoogleAuthError` (creds missing) → `warn` (not fail — opted out).
  - `[google]` extras missing → `warn` ("install `cosinabox[google]`").
- `Check` ABC gains `network: bool = False`. Existing checks default False; new check is the only one with True.
- `cosinabox doctor` gains `--offline` flag that filters checks where `network=True` at the registry level.
- Email labels read from `integrations.yaml` (mirroring Initiative A's `_load_google_accounts`); fallback to `#1`/`#2`/etc. when accounts are configured only via env vars.
- Drive-by fix: `pre-commit` secret-scan hook self-matched `src/cosinabox/doctor/checks.py` (its `_SECRET_PATTERNS` regex contains the literal sentinel prefixes by design). Hook restructured to:
  - Extend the exclude list to cover `checks.py` (mirrors the existing `.pre-commit-config.yaml` exclusion).
  - Capture grep's filename output and check `[ -n ... ]` instead of relying on the pipeline exit code (macOS BSD `xargs` exits 0 on empty input, which had been spuriously tripping `&& exit 1` whenever every staged file was excluded).
- 7 new check tests + 4 new doctor-CLI tests. 990 unit tests green.

## What was planned vs what shipped

| Milestone | Planned | Actual | Note |
|---|---|---|---|
| M1 — Sign-off | 0 | 0 | Q1–Q5 signed off in chat |
| M2 — Check class + Check ABC change | 45 min | ~30 min | TDD per task; existing tests untouched (`network` default = False is backwards-safe) |
| M3 — `--offline` flag | 20 min | ~10 min | Single-line filter at the registry traversal |
| M4 — Register the check | 10 min | ~5 min | One-line add to REGISTRY |
| M5a — Structural smoke (Claude) | 15 min | ~10 min | Hit Google's real OAuth endpoint with a bad token; got `RefreshError` as expected — partial real-API smoke that PR #86 didn't have |
| M5b — Real-Google smoke (maintainer) | 5 min | DEFERRED | Required gate, not run yet |
| M6 — PR | 15 min | ~10 min | |
| Drive-by — pre-commit fix | 0 | ~30 min | Pre-existing bug surfaced when staging the M2 edits; fixed in same PR |

**Total:** ~95 min on the planned work + ~30 min on the unplanned hook fix = ~125 min. Plan budget was ~110 min. ~115% of plan once the unplanned fix is included; ~86% on planned work alone.

## What went well — keep doing

- **M5a actually exercised real Google OAuth.** With an intentionally-invalid token (`GOOGLE_OAUTH_REFRESH_TOKEN_1=intentionally-invalid-token`), the check made a real HTTPS call to Google's OAuth endpoint and Google returned `RefreshError`. That's the kind of real-API smoke PR #86 deferred — and it landed in the PR description as an evidenced JSON snippet, not "tests are green, trust me."
- **`network: bool = False` as a Check ABC default.** Backwards-compat safe (10 existing checks didn't need any change), and the new flag is wired in one place (`cli/doctor.py`) instead of per-check.
- **Late import of `google.auth.exceptions` and `google.auth.transport.requests` inside `run()`.** Keeps the check module loadable when `[google]` extras are missing; the warn-and-skip path triggers cleanly.

## What didn't — change next time

- **Pre-commit hook bug ate ~30 min of unplanned debugging.** The hook had two latent issues (self-matching `checks.py`; macOS `xargs` no-run-if-empty). Surface this proactively in future plans that touch `doctor/checks.py` or any file where the secret-scan literals appear in source. Zero-effort signal: if the file contains any of the four sentinel token-format prefixes the hook regex matches, expect the hook to fire on commit.
- **M5b passed cleanly.** Maintainer ran `railway run .../cosinabox doctor --json | jq '.[] | select(.name == "oauth_refresh_live")'` against the live `rovik-keevs` deploy: `{"status": "pass", "message": "All 2 Google account(s) refreshed cleanly."}`. Both accounts (`rovik@majiq.agency` and `rovik@cantina.ai`) refreshed successfully against Google's OAuth endpoint. PR #88 merged after sign-off — discipline validated, no follow-up bugs surfaced.
- **CI caught a count assertion I missed.** `tests/integration/test_e2e_setup.py:41` hard-coded `len(data) == 10` for the doctor JSON output; new check brought it to 11. I updated the same assertion in `test_cli_doctor.py` during M3 but didn't grep the whole test tree. **Lesson:** when adding to a registry that's count-asserted in tests, grep across `tests/**` for `len(...) ==` patterns before pushing. Pre-merge CI is the safety net but it's wall-clock-expensive (~3 min round-trip per push) compared to a 1-second grep. Captured as a follow-up item: consider replacing count assertions with set assertions (`{check.name for check in REGISTRY} == expected_set`) so adding a check fails the test with a useful diff instead of an integer mismatch.

## Estimate calibration update

This was a CLI-wrapper plan (`cosinabox doctor` shells out via `cred.refresh()` to Google's OAuth endpoint). It clocked ~86% of plan on the planned work alone — which lines up with the "wrapper plans cost ~70%" rule from PR #87's retro, plus the ~30-min unplanned fix. **Confirms the rule: any plan touching an external runtime (`subprocess` to a CLI, HTTP to a third-party API, etc.) should budget for ~80% of plan + ~30 min of "first-real-run surprise."**

## Commitment violations

None of CLAUDE.md's safety rules. Pre-commit hooks were not bypassed (the hook fix preserves the discipline; it removes a false-positive). Worktree from session start. Plan-as-source-of-truth held.

## New lessons → memory candidates

- **The pre-commit secret-scan hook has a known false-positive surface.** Files containing literal copies of the secret-scan regex's sentinel prefixes (the four token-format prefixes the hook looks for) will self-match unless excluded. Surface to the maintainer if a future PR adds another such file (e.g. a wider regex audit, a sample integration that documents the prefixes). One-line addition to the exclude list in `.pre-commit-config.yaml`.
- **xargs no-run-if-empty on macOS.** BSD `xargs` exits 0 when stdin is empty; GNU `xargs -r` opts in to that behavior. Either way, `xargs ... && exit 1 || exit 0` patterns are footguns when the upstream filter can drop everything. Prefer capturing output and checking `[ -n "$out" ]`.

## Out of scope / follow-ups

- **M5b** maintainer smoke against `rovik-keevs` — required before merging PR #88.
- **Per-check timeout** for the refresh call. Defer until someone reports a hang.
- **Caching the refresh-check result for N minutes.** Defer; doctor isn't a hot path.
- **Initiative C** (`/status` per-account auth + alert enrichment) — separate plan and PR (#89), shipping in parallel.
