# OAuth UX rework — design spec

**Date:** 2026-05-06
**Status:** Draft
**Scope:** Make Google OAuth re-auth tractable for OSS users. Remove the multi-system scavenger hunt that exists today.

## Problem

Re-authenticating an expired Google refresh token is currently the worst UX in the engine. A first-time OSS user has to:

1. Know that Google Cloud Console exists, find the project, find the OAuth client.
2. Pull two creds out of Railway env vars — and beat `railway variables`'s default truncation.
3. Have a working local `cosinabox` install with `[google]` extras (and re-run `pip install -e .` if their venv is stale).
4. Export env vars locally.
5. Manage browser-account state — the consent screen will use whichever Google account the browser is signed into.
6. Run an interactive browser flow.
7. Manually copy a refresh token between three different surfaces.
8. Know the magic naming convention `GOOGLE_OAUTH_REFRESH_TOKEN_<N>` and which N corresponds to which Gmail account.
9. Update Railway with the new token.
10. Redeploy and watch logs to verify.

A single session walking the engine maintainer through this hit four separate failure modes in five minutes — and the maintainer **wrote** the engine. A stranger has no chance.

### Specific failures observed in production (2026-05-06 session)

| # | Failure | Root cause |
|---|---|---|
| 1 | `ModuleNotFoundError: cosinabox.cli` | Local venv was set up before the `cli` package existed; `pip install -e .` was never re-run. |
| 2 | `Error 401: invalid_client` | `railway variables` table view truncated the long suffix on `GOOGLE_OAUTH_CLIENT_ID`. |
| 3 | Wrong Google account in consent | Browser was signed into personal Gmail; consent screen offered no warning. |
| 4 | Auth-health keeps flagging account #2 after re-auth | Consent completed with the wrong account; produced a working-but-wrong refresh token. Silent corruption. |
| 5 | `_REFRESH_TOKEN_N` numbering is invisible | The mapping "N=2 means rovik@cantina.ai" exists only in the maintainer's head. |
| 6 | Account-revoked is not surfaced until next briefing has empty calendar/email | `_runtime_alert` was not wired (separate bug, fixed in same PR). |

Failures (1)–(4) are addressed by tactical fixes in the current PR (`--account` flag, alert account labels, instructions). Failures (5)–(6) and the underlying ten-step flow are this spec's domain.

## Goals

1. **Refresh in one command.** A returning user runs one well-named CLI command, picks an account from a list, completes the browser flow, and is done. No manual env-var copying.
2. **First-time setup is conversational.** New users follow the existing `cosinabox interview` and never see a refresh token.
3. **Health is observable.** Users see per-account auth status in `/status` and get actionable Telegram alerts on degradation.
4. **No locally-installed cosinabox required.** Bonus goal: the deployed bot itself can drive the flow via a magic link, eliminating the local-install dependency entirely.

## Non-goals

- Replacing Google OAuth with another auth backend.
- Supporting OAuth flows for non-Google integrations (Fireflies, Attio) — separate spec.
- Eliminating the need for the user to have a Google Cloud project configured at all (would require us to host one shared across users — security/scope explosion).

## Design

The work splits into four orthogonal initiatives, in ascending order of complexity. Each is independently shippable.

### Initiative A: `cosinabox auth refresh` orchestration

**One command that does everything between "I need to re-auth" and "the deploy is healthy".**

```
cosinabox auth refresh
```

Behavior:
1. Reads `integrations.yaml` from the user's local user-repo (or `--config-dir`). Lists the configured Google accounts.
2. If multiple accounts: prompts user to pick which one.
3. Detects the deployment target. v0.1: Railway via `railway whoami` + `railway link` state. Future: AWS, Fly, generic.
4. Pulls `GOOGLE_OAUTH_CLIENT_ID` + `GOOGLE_OAUTH_CLIENT_SECRET` from the deployment env (via `railway variables --json`).
5. Runs the existing `cosinabox auth google --account <picked-email>` flow.
6. On success, updates the right `GOOGLE_OAUTH_REFRESH_TOKEN_<N>` env var on the deployment.
7. Triggers a redeploy.
8. Tails logs for the next `auth_health` run; reports pass/fail.

Scope of work: ~1 day. New module `cosinabox/cli/auth_refresh.py`. Dependencies: existing `cosinabox auth google --account` (shipped in current PR).

Reversibility: this is a wrapper. Users who don't trust automation can keep using the manual flow. The `--account` flag we shipped today is the load-bearing primitive.

### Initiative B: `cosinabox doctor` actively probes refresh tokens

Today `cosinabox doctor` validates static config (file existence, schema). It does not test that the refresh tokens actually work.

Add a new check to `src/cosinabox/doctor/checks.py`:

```python
def check_google_oauth_refresh(integrations, env) -> CheckResult:
    """Mint a fresh access token for each configured Google account.

    Catches dead refresh tokens proactively instead of waiting for the next
    morning_briefing to render an empty calendar.
    """
```

The check loops over `build_all_credentials()`, attempts a `creds.refresh(Request())`, and reports pass/fail per account. Failures include the account email and the suggested fix command (`cosinabox auth refresh` after Initiative A ships).

Scope of work: half a day. Live network check, so doctor gets `--offline` flag to skip when no internet (e.g., CI).

### Initiative C: `/status` and Telegram alerts surface per-account auth

Two surfaces:

**`/status` extension** — show per-account auth health inline:

```
Name: Rovik
Timezone: Asia/Singapore
Tools: 20 (...)
Jobs: morning_briefing, evening_wrap, ...
Stakeholders: 50
OAuth: ✓ rovik@majiq.agency | ✗ rovik@cantina.ai
```

This requires `auth_health`'s last-known per-account status to be persisted in SQLite (currently it only logs).

**Alert message enrichment** — already partially landed in current PR (account label). Extend to include direct copy-pasteable next-step command:

```
[auth] Google OAuth token expired for rovik@cantina.ai (account 2).
Run: cosinabox auth refresh
```

Scope: half a day after Initiative A lands.

### Initiative D: web-based OAuth flow served by the bot itself

Eliminates the local-install requirement. The deployed bot exposes a tiny endpoint:

```
GET /auth/google/start?account=rovik@cantina.ai
  → 302 to Google consent
  → callback writes new refresh token to its own env (Railway API)
  → 200 with success page
```

User experience from Telegram:
```
[auth-health-alert] OAuth dead for rovik@cantina.ai. Re-auth here:
https://rovik-keevs.up.railway.app/auth/google/start?token=<short-lived>
```

User clicks link → completes consent in any browser → redeploy auto-triggers → done. No CLI, no env-var copying, no local install.

Caveats:
- Requires the bot to expose an HTTP listener (currently Telegram-only, polling). Adds attack surface.
- The token-write back to Railway env requires `RAILWAY_TOKEN` in the deploy env — gives the deploy permission to mutate its own config. Acceptable but new.
- Magic-link tokens need expiry (5 min) and one-shot semantics to prevent replay.

Scope: 2-3 days. v0.2 territory. Defer until A+B+C are landed and stable.

## Migration / backwards compatibility

All four initiatives are additive. Existing flows (`cosinabox auth google` without `--account`, manual env-var updates) keep working. No schema or config-file changes. New CLI commands are net-new.

## Open questions

1. **What's the right deployment-target abstraction?** v0.1 Railway-only is fine. But when AWS/Fly land, do we abstract behind `cosinabox.deploy.targets`? Or punt and ship Railway helpers, let other targets re-implement?
2. **Should `/status` show OAuth per-account even for single-account users?** Probably yes — uniformity beats hiding the row.
3. **Does Initiative D's web endpoint break the "Telegram-only output" simplicity?** Minor philosophical question. The endpoint only exists during the OAuth flow window — could be a tiny ephemeral server.

## Sequencing

Ship A → B → C in this order. Each gets its own plan + retro. D goes in a separate plan once A–C are stable.

## Related

- Current PR `feat/tz-fix-and-runtime-alert` ships `--account` flag, alert account labels, and `set_account_emails` wiring — the primitives Initiative A depends on.
- `docs/specs/2026-04-17-auth-health-watcher-design.md` — the existing auth-health background, which Initiative B extends.
