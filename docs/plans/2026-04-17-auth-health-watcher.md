# Plan: Auth-Health Watcher Implementation

**Status:** Not started.
**Spec:** `docs/specs/2026-04-17-auth-health-watcher-design.md`
**How to resume:** open this file, find the first `- [ ]` milestone, read its "Files touched" + "Tests" sections, start there. The plan is self-contained; do not rely on chat context.

## Context / Why

2026-04-17 incident: a cosinabox deployment looped `invalid_grant: Token has been expired or revoked` for days without surfacing any alert. The evening_wrap job ran and produced degraded output that only a human noticed. The spec describes a scheduled job that checks refresh tokens and alerts on transitions. This plan implements it.

## Non-goals

- No changes to `build_all_credentials()` or any Google auth internals.
- No new admin-chat abstraction (alerts go to the user's primary Telegram chat via the existing `wire_telegram_output` pipe).
- No other auth types (Fireflies, Anthropic, Attio) — Google only in this plan.
- No liveness/heartbeat monitoring.

## Milestones

### M1 — Write the failing test

**Files touched:** `tests/unit/jobs/test_auth_health.py` (new).
**Tests:** TDD — these start red.

- [ ] Create test file with the following cases (mocking `credentials_factory`):
  - `test_no_creds_configured_returns_empty`: factory raises `GoogleAuthError` → `run()` returns `""`, no state change.
  - `test_single_healthy_cred_returns_empty`: factory returns one cred whose `.refresh()` succeeds → `""`.
  - `test_single_broken_cred_emits_failure_text`: factory returns one cred whose `.refresh()` raises `RefreshError` → return includes `"Google auth failed for account #1"` and the fix instructions.
  - `test_still_broken_on_second_tick_is_silent`: two consecutive ticks with same broken cred → first returns failure text, second returns `""`.
  - `test_recovery_emits_restored_text`: broken on tick 1, healthy on tick 2 → tick 2 returns `"Google auth restored for account #1"`.
  - `test_transport_error_does_not_change_state`: broken on tick 1, `TransportError` on tick 2, healthy on tick 3 → tick 2 returns `""` (state preserved as broken); tick 3 returns recovery text.
  - `test_two_creds_one_fails_one_healthy`: two creds, #1 ok, #2 `RefreshError` → return includes `"account #2"`, not `"account #1"`.
  - `test_both_failing_and_recovering_in_same_tick`: #1 recovers, #2 newly fails → return has both sections joined by blank line.
  - `test_restart_re_alerts_still_broken`: simulate a fresh `AuthHealthJob` instance (new `_health` dict) with broken cred → first call emits failure text again.
- [ ] Run `pytest tests/unit/jobs/test_auth_health.py` — confirm all tests fail with `ModuleNotFoundError` or `AttributeError`.

**Estimate:** 30 min.

### M2 — Implement `AuthHealthJob`

**Files touched:** `src/cosinabox/jobs/auth_health.py` (new), `src/cosinabox/defaults.py`.
**Tests:** M1 test file turns green.

- [ ] Create `src/cosinabox/jobs/auth_health.py`:
  - `AuthHealthJob(Job)` with `name = "auth_health"`.
  - `__init__(*, credentials_factory=build_all_credentials)`.
  - `_health: dict[int, bool]` initialized to `{}` per instance.
  - `run(context: JobContext) -> str`:
    - Try `creds = list(self.credentials_factory())`; on `GoogleAuthError` return `""`.
    - For each `(i, cred)` in `enumerate(creds, start=1)`:
      - Try `cred.refresh(Request())`. Success → `ok=True`. `RefreshError` → `ok=False`. Other exception → log warning, `continue` (preserve prior state).
      - Compare with `self._health.get(i)`. On `ok=False` and prev != False: append to `newly_failed`. On `ok=True` and prev is False: append to `newly_recovered`. Update `self._health[i] = ok`.
    - Build return string: failure section + blank line + recovery section (whichever are non-empty). Empty string if nothing.
- [ ] Add to `src/cosinabox/defaults.py`:
  ```python
  # Auth-health watcher cadence. Every 15 min is short enough that a
  # revoked-token alert reaches the maintainer within a meeting-length
  # window, and long enough that we don't spam the Google token-refresh
  # endpoint. Chosen 2026-04-17 after an incident where a revoked
  # refresh token looped `invalid_grant` silently for days — see
  # docs/specs/2026-04-17-auth-health-watcher-design.md.
  AUTH_HEALTH_DEFAULT_SCHEDULE: str = "*/15 * * * *"
  ```
- [ ] Run M1 tests — all green.

**Estimate:** 30 min.

### M3 — Register the job

**Files touched:** `src/cosinabox/app/jobs.py`.
**Tests:** integration check via `pytest tests/` (existing suite stays green).

- [ ] Edit `register_core_jobs` in `src/cosinabox/app/jobs.py`:
  - After the existing loop, add an unconditional registration block:
    ```python
    # auth_health: always-on by default; registered outside the iteration
    # loop so existing user repos whose jobs.yaml predates this change
    # still get silent-failure protection.
    from cosinabox.jobs.auth_health import AuthHealthJob
    from cosinabox import defaults

    auth_health_cfg = jobs_config.get("auth_health", {})
    if auth_health_cfg.get("enabled", True):
        cron = auth_health_cfg.get("schedule", defaults.AUTH_HEALTH_DEFAULT_SCHEDULE)
        scheduler.add_job(AuthHealthJob(), cron=cron)
        logger.info("Registered auth_health at %s", cron)
    ```
- [ ] Run full suite: `pytest`.

**Estimate:** 20 min.

### M4 — Template + discovery

**Files touched:** `src/cosinabox/templates/user-repo/jobs.yaml`, `src/cosinabox/templates/user-repo/docs/agent/editing-config.md`.
**Tests:** `pytest tests/` (template loading tests should still pass).

- [ ] Add to `jobs.yaml` template (before `morning_briefing` is fine — ordering is alphabetical-ish):
  ```yaml
  auth_health:
    enabled: true
    schedule: "*/15 * * * *"   # every 15 min — alerts on revoked Google tokens
  ```
- [ ] Update `docs/agent/editing-config.md` job list to mention `auth_health` (one-line entry).
- [ ] Run `pytest` + `cosinabox validate` against the template.

**Estimate:** 15 min.

### M5 — Commit, PR, merge

**Files touched:** none (git only).
**Tests:** CI on the PR.

- [ ] Commit M1–M4 as a single feat commit: `feat(auth-health): proactive watcher for revoked Google tokens`.
- [ ] Push to `feat/auth-health-watcher`.
- [ ] `gh pr create ... && gh pr merge --auto --squash`.

**Estimate:** 10 min.

## Out of scope / follow-ups

- Persisting `_health` to the memory DB so restarts don't re-alert. Defer until spam becomes a problem.
- An admin-only Telegram chat (`telegram.admin_chat_id`) separate from the user chat. Spec explicitly punts this to a future spec.
- Watchers for Fireflies / Anthropic / Attio. Add only if silent-failure incidents occur for those.
