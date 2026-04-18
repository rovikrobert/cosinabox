# Cosinabox Auth-Health Watcher — Design Spec

**Date:** 2026-04-17
**Status:** Approved
**Scope:** Add a proactive Google auth-health check to cosinabox so deployments alert on silent token revocation instead of looping `invalid_grant` invisibly.

## Problem

On 2026-04-17 a cosinabox deployment was observed looping `invalid_grant: Token has been expired or revoked` every minute for an indeterminate number of days. No alert surfaced. Scheduled jobs like `evening_wrap` still ran — they just produced messages with no live Gmail/Calendar content, and a human noticed the output was wrong.

Cosinabox has no proactive check that surfaces this kind of silent degradation. The closest thing is the startup-time `send_auth_error_alert` (`src/cosinabox/app/alerts.py:31`), which only fires at process start — token revocation mid-run goes unnoticed until the next deploy.

## Approach

**Each deployment monitors its own Google accounts via a scheduled in-process job.** On a transition to unhealthy, the bot alerts its own Telegram chat. On recovery, it alerts again.

Rejected alternatives:
- *External health-check (GitHub Action, uptime monitor)* — more moving parts, requires a new HTTP endpoint. Overkill for single-tenant self-hosted deployments.
- *Cross-deployment watchers* — require sharing OAuth secrets across deployments. Tight coupling, security concern.

## Design

### 1. New job: `cosinabox.jobs.auth_health`

File: `src/cosinabox/jobs/auth_health.py`

Follows the existing sync `Job` pattern (`src/cosinabox/jobs/base.py`). No injected dependencies beyond the optional factory for testing:

```python
class AuthHealthJob(Job):
    name = "auth_health"

    def __init__(self, *, credentials_factory=build_all_credentials):
        self.credentials_factory = credentials_factory
        self._health: dict[int, bool] = {}

    def run(self, context: JobContext) -> str:
        ...  # returns alert text, or "" when no transition
```

**Alerting flow**: the job returns alert text (or empty string when no transition). `cosinabox.app.alerts.wire_telegram_output` monkey-patches each registered job's `run` (see `src/cosinabox/app/alerts.py:48`) and pipes non-empty returns to Telegram as `[auth_health]\n\n<text>`. This matches the `morning_briefing`/`evening_wrap` pattern and avoids a separate `send_alert` injection.

Registered in `app/jobs.register_core_jobs` (no `send_telegram` dependency at construct time). Default cron lives in `jobs.yaml` template and `defaults.py`.

### 2. Check logic

For each credential in `enumerate(self.credentials_factory(), start=1)` — the index mirrors the `GOOGLE_OAUTH_REFRESH_TOKEN_{i}` env-var position (see `src/cosinabox/tools/google/auth.py:68`):

1. Attempt `creds.refresh(Request())` inside a try/except.
2. **`RefreshError`** → mark unhealthy. This is the only exception class that indicates a real revocation. Google's `google-auth` raises it for `invalid_grant`, `invalid_client`, and related OAuth failures.
3. **Success** → mark healthy.
4. **Any other exception** (`TransportError`, `TimeoutError`, etc.) → log as warning; **do not change health state**. This prevents flapping alerts on transient network errors.

**Handling missing configuration**: `build_all_credentials()` raises `GoogleAuthError` when `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` are unset (user has google integration disabled). Catch it at the top of `run()` and return early with empty string — a deployment without Google configured is not broken, it's just not using the integration.

No human labels (cosinabox is multi-account by position, not by name).

### 3. State + transitions

In-memory dict keyed by token index:

```python
_account_health: dict[int, bool] = {}
```

- `ok=False`, previously `True` or unknown → append to `newly_failed`.
- `ok=True`, previously `False` → append to `newly_recovered`.
- No transition → nothing appended.

After the loop, `run()` joins any `newly_failed` / `newly_recovered` messages into the return string. Empty string if no transitions.

**Restart behavior**: on process restart, `_health` is empty; the first tick re-alerts any still-broken account. Rationale: a restart is a useful re-prompt. Tradeoff noted: if a cred is broken for days and the service redeploys frequently, every deploy produces one alert. Accept that as the cost of not persisting state — fixing the cred is the way to stop the alerts.

### 4. Alert text

Delivery is through `wire_telegram_output` (see section 1). The job only produces the body; the `[auth_health]\n\n` prefix is added by the wrapper.

**Body on failure** (one line per failed index, joined with newlines):
```
Google auth failed for account #{i}.
Gmail and Calendar reads will be silently skipped until re-auth.
Fix: `cosinabox auth google`, update GOOGLE_OAUTH_REFRESH_TOKEN_{i} on Railway, redeploy.
```

**Body on recovery**:
```
Google auth restored for account #{i}.
```

If both `newly_failed` and `newly_recovered` are non-empty on the same tick (rare but possible), concatenate with a blank line between sections.

No admin-channel abstraction in this spec. A future spec can add `telegram.admin_chat_id` if alerts should diverge from the user-facing chat; for now the primary chat is the right place — the user is the ops owner.

### 5. Wiring

- Register `AuthHealthJob` in `register_core_jobs` in `src/cosinabox/app/jobs.py`. It doesn't need `send_telegram` at construct time — `wire_telegram_output` (which runs after registration in `_core.py`) handles delivery.
- Add to `src/cosinabox/templates/user-repo/jobs.yaml` with `enabled: true` by default.
- Add to `src/cosinabox/defaults.py`: `AUTH_HEALTH_DEFAULT_SCHEDULE = "*/15 * * * *"` with a comment citing this spec and 2026-04-17's incident.

**Registration must be robust against missing config keys.** The other jobs in `register_core_jobs` iterate `for job_name, cfg in jobs_config.items()` — if a user's `jobs.yaml` doesn't contain `auth_health` (as is the case for every existing user repo today), the loop skips it and silent-degradation protection never activates. To avoid this footgun:

Register `auth_health` **outside the iteration loop**, using `jobs_config.get("auth_health", {"enabled": True, "schedule": defaults.AUTH_HEALTH_DEFAULT_SCHEDULE})` as the effective config. Users who want to disable can add `auth_health: { enabled: false }` to their `jobs.yaml` explicitly. This keeps the default-on behavior without requiring every existing user to run a migration.

No `jobs.schema.json` change — the schema uses `additionalProperties` so any new job key is already valid.

No `schema_version` bump — new jobs are additive and don't break existing configs.

### 6. Interaction with existing `doctor` command

`cosinabox doctor` already checks credentials at invocation time. This watcher is the *runtime* complement — doctor is one-shot, watcher is ongoing. No conflict.

## Testing

File: `tests/unit/jobs/test_auth_health.py`. Inject `credentials_factory` that returns mock `Credentials` whose `.refresh()` raises / succeeds on command. Assert `run()` returns the expected string.

Test cases:
- **No creds configured**: factory raises `GoogleAuthError` → `run()` returns `""`, no state change.
- **One healthy, one revoked**: factory returns 2 creds; one's `.refresh()` raises `RefreshError`, other succeeds → `run()` returns failure text for index 2 (say), healthy state for 1.
- **Transition recovery**: first tick has index 1 broken (alert fires); second tick has it fixed → recovery alert text returned.
- **Both failing and recovering in same tick**: rare case (index 1 recovers, index 2 fails) → concatenated body.
- **Still-broken on restart**: after `_health` is cleared, first tick with broken cred still emits the failure text (by design).
- **Transient `TransportError`**: does not change state, does not emit a transition alert. Log-only.
- **Consecutive healthy ticks**: returns `""` on every call after the initial alert.

## Out of scope

- **Liveness heartbeat** (detecting the bot process itself being down). If the deployment crashes, this watcher can't alert. Separate problem; host-platform deploy status + Telegram bot polling already gives partial coverage for most setups.
- **Other auth types** (Fireflies, Anthropic, Attio). Add in follow-ups only if they cause silent failures in practice.

## Migration / rollout

1. Land the job with `enabled: true` in the default `jobs.yaml`. No feature flag — the `enabled` toggle already acts as one.
2. Deploy to a live cosinabox instance. Verify the job runs on schedule (visible in scheduler logs) and emits no false alerts.
3. Acceptance test: set `GOOGLE_OAUTH_REFRESH_TOKEN_1` to a known-bad value in staging, confirm alert fires within 15 min. Restore, confirm recovery alert fires.

No backfill needed — the watcher is forward-looking only.
