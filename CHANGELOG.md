# Changelog

All notable changes to cosinabox will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `SECURITY.md` — security policy and private vulnerability reporting channel via GitHub Security Advisories.

### Changed
- README job count corrected from "5 built-in jobs" to "13" (existing breadth was undersold).
- `pyproject.toml` author updated to "Rovik Robert" (was "Cantina").
- `docs/agent/jobs.md` (user-repo template) now lists the `auth_health` job that already ships enabled by default.
- New `defaults.TRANSCRIPT_TITLE_MIN_TOKEN_CHARS` (3) replaces an inline `len(w) > 2` in the debrief matcher, per CLAUDE.md rule 3. (#94)

### Fixed
- README and CONTRIBUTING.md `git clone` placeholder URL (`github.com/user/cosinabox`) replaced with the real URL.
- User-repo template `CLAUDE.md` engine-docs link no longer points at a non-existent `cosinabox/cosinabox` org with internal lore in parentheses.
- `pip install cosinabox[consult]` no longer installs a broken consult server. The `mcp` requirement was unbounded (`>=1.12`), so a fresh resolve picked up **mcp 2.0.0**, which removed the `mcp.server.fastmcp` package `consult/server.py` imports — the 2.0.0 wheel ships no `fastmcp` path at all. Now capped at `>=1.12,<2` in both the `consult` and `dev` groups. CI was green only because earlier runs predated the 2.0.0 release; it went red on the next PR against an untouched file.
- `post_meeting_debrief` no longer reports "no transcript" for a meeting whose transcript exists. Title-word overlap dropped every token under 3 characters, discarding short letter+digit words like `Q3`, `V2` or `F1` — frequently the only word two titles share, and the only signal available at all when a transcript source populates `participants` with the owner alone (which makes the attendee-overlap check a no-op). Titles are now split on punctuation too, so `Q3-planning` can overlap `Q3 planning` and `budget,` can overlap `budget`. Time proximity stays mandatory, so nothing outside `TRANSCRIPT_TIME_WINDOW_SECONDS` can be pulled in, and bare numbers (`10`) plus short pure-alpha words (`go`) stay filtered as noise. (#94)

## [0.1.6] — 2026-05-06

OAuth UX rework — Initiatives A → C of `docs/specs/2026-05-06-oauth-ux-rework.md`. Re-authenticating an expired Google refresh token used to be a 10-step manual scavenger hunt across Google Cloud Console, Railway, a local terminal, and Telegram. After this release, it's one command, one browser consent, and a Telegram alert that confirms the new token works.

### Added
- `cosinabox auth refresh` — single-command Google OAuth re-auth orchestrator. Reads `integrations.yaml`, picks an account (auto-selects single-account; numbered picker for multi-account; `--account <email>` for non-interactive), pulls OAuth client creds from the linked Railway service, runs consent in the browser, writes the new refresh token back to Railway, and triggers a redeploy. The next `auth_health` tick (≤15 min) confirms the new token works and Telegrams the user if it doesn't. Initiative A. (#86, #87, #90)
- `cosinabox doctor` actively probes refresh tokens. New `oauth_refresh_live` check loops `build_all_credentials()` and attempts `cred.refresh(Request())` per account, reporting `pass` / `fail` / `warn` (with the failing account's email and `Run: cosinabox auth refresh` hint). Catches dead tokens proactively rather than waiting for the next briefing to render an empty calendar. Initiative B. (#88)
- `cosinabox doctor --offline` flag — skips checks that require network access (e.g. the new live OAuth probe). Lets doctor run in CI / on planes without spurious failures. Backed by a new `network: bool = False` attr on the `Check` ABC. (#88)
- `/status` Telegram command appends per-account OAuth health: `OAuth: ✓ rovik@majiq.agency | ✗ rovik@cantina.ai`. Hidden on fresh deploys until the watcher's first tick — uniformity for empty state would be noise. Initiative C. (#89)
- `auth_health_status` SQLite table inside `memory.db` persists per-account refresh-token state. PK on account_index; transient errors don't write so prior known state survives network blips. Read by `/status`. (#89)
- Pre-commit secret-scan hook gained `src/cosinabox/doctor/checks.py` to its exclude list and was rewritten to handle the "all staged files excluded" case (macOS xargs no-run-if-empty edge). The doctor file's `_SECRET_PATTERNS` regex contains the literal sentinel prefixes by design — same self-match the existing `.pre-commit-config.yaml` exclusion was added for. (#88)

### Changed
- Auth-health Telegram alert template (`auth_health.py:_FAILURE_TEMPLATE`) and runtime OAuth alert (`_runtime_alert.py`) now both end with `Run: cosinabox auth refresh`. Replaces the legacy three-step "auth google + update GOOGLE_OAUTH_REFRESH_TOKEN_<N> on Railway + redeploy" instruction wherever it appeared in user-facing strings. (#89)
- User-repo template `oauth-walkthrough.md` leads with the `cosinabox auth refresh` flow; the manual ten-step GCP-console flow stays as fallback for first-time setup, non-Railway deploys, and the case where the new command itself errors. (#86)
- `_railway.set_variable` passes the value via `--stdin` (kept out of argv so other users on the box can't see it via `ps -ef`) and `--skip-deploys` (so it doesn't kick off its own deploy and race with `_railway.redeploy()`). Determines the orchestrator's flow as `set` → `redeploy`, no implicit deploys. (#87, #90)
- `_railway.redeploy` failures now include the captured Railway CLI stderr/stdout in the user-facing error so the actual cause is visible. `set_variable` keeps stripping captured output (Railway can echo the value back on validation errors). Differential leak avoidance. (#90)

### Fixed
- Stress-test pass post PR #86 caught six bugs against the real `railway` CLI 4.30.2: `railway status --json` schema mismatch (`name` / `services.edges[].node.name`, not `projectName`/`serviceName`); `wait_for_deployment` polled `latestDeployment.status` which doesn't exist in railway 4.x output (function removed entirely; `auth_health` is the verification path); refresh token went through argv (now `--stdin`); `set_variable` error string echoed captured stdout/stderr (now hides them); orchestrator caught typed exceptions but not `RuntimeError` from `mint_refresh_token` (missing `[google]` extra) — now caught and surfaced as a friendly ClickException; malformed `integrations.yaml` raised a raw YAML traceback (now wrapped). (#87)
- Race condition between `set_variable`'s implicit deploy (Railway's default) and `auth refresh`'s explicit `redeploy()` — caught by M8 manual smoke against `rovik-keevs`. (#90)
- `tests/integration/test_e2e_setup.py` doctor count assertion updated 10 → 11 for the new `oauth_refresh_live` check. CI caught what unit tests missed. (#88)

### Docs
- Three retros: Initiative A (`oauth-auth-refresh`, with two addenda for PR #87's six-bug stress test and PR #90's M8 race fix), Initiative B (`doctor-oauth-probe`, with M5b real-Google smoke recorded as pass), Initiative C (`status-and-alerts`).
- Three plans: `2026-05-06-oauth-auth-refresh.md`, `2026-05-06-doctor-oauth-probe.md`, `2026-05-06-status-and-alerts.md`.
- `feedback_cli_wrapper_smoke_test.md` (maintainer's private memory): manual smoke is non-negotiable before merge for plans that subprocess to external CLIs. Validated three times this release: PR #87 found six bugs (deferred-then-stress-tested), PR #88 passed clean (rule working), PR #90 found a race condition (M8 ran late but caught real-world delta).

## [0.1.5] — 2026-05-06

### Fixed
- Cron triggers now fire in the user's configured timezone instead of the OS-local one. `CronTrigger.from_crontab()` defaults to `tzlocal.get_localzone()`, which on Railway (UTC container) silently shifted every cron-scheduled job by the user's UTC offset — `morning_briefing` at `0 8 * * *` with `personality.md` `timezone: Asia/Singapore` was firing at 16:00 SGT instead of 08:00 SGT. `SchedulerRunner.add_job` now passes `timezone=ZoneInfo(get_timezone())` explicitly. (#85)
- Runtime OAuth alert now reaches Telegram. `set_send_telegram()` was defined since the runtime-alert PR but never called from production startup, so every token expiration during a scheduled job logged "no Telegram configured" silently instead of paging. Wired in `App.run()` right after `make_send_telegram()`. (#85)
- User-repo template `Dockerfile` uses `pip install --upgrade --upgrade-strategy eager`. Without it, pip's default skip-if-pin-already-satisfied keeps deploys frozen on the baked-in cosinabox version even when the floating `:0.1` runtime tag has been retagged to a newer patch — bit us live: rovik-keevs ran 0.1.2 even after 0.1.4 had shipped. (#85)

### Added
- `jobs.yaml` per-job `timezone:` field is now honoured. Threads through `SchedulerRunner.add_job(*, cron, timezone=None)` so a user can run e.g. `morning_briefing` in their local zone while keeping `auth_health` on UTC. (#85)
- `/timezone` Telegram command (ported from cos-agent). No args: shows current TZ + local time. With arg: resolves via fuzzy matcher, persists to SQLite, and reschedules every cron-trigger job in place — so users travelling to a new TZ don't have to edit `personality.md` and redeploy. (#85)
- `App.run()` now calls `load_timezone_override()` at boot, giving the persisted `/timezone` override precedence over `personality.md`. The function existed since timezone.py landed but was never called, which meant runtime TZ changes were silently lost on the next restart. (#85)
- `cosinabox auth google --account <email>` flag verifies the consented Google account matches before printing the refresh token. Eliminates the silent-corruption mode where a stray browser session could mint a token for the wrong inbox. Mismatch raises `ClickException` with both emails shown and refuses to leak the token. (#85)
- Runtime OAuth alerts now name the failing account in multi-account setups: `OAuth token expired for rovik@cantina.ai (account 2)`. App boot populates `set_account_emails()` from `integrations.yaml`'s `google.accounts` list. (#85)

### Docs
- Added `docs/specs/2026-05-06-oauth-ux-rework.md` scoping the broader OAuth UX rework (one-shot `auth refresh` orchestration, doctor active probe, per-account `/status` surface, web-based OAuth flow). Spec only — implementation lands separately.

## [0.1.4] — 2026-04-21

### Fixed
- Release workflow's "Wait for PyPI" step no longer races the CDN. The previous version curled the `/simple/` index from the GitHub Actions runner, which could succeed at the same moment pip (inside docker buildx, different network path) still saw stale data. 0.1.3's runtime image build failed with `No matching distribution found for cosinabox==0.1.3` for this reason. Replaced with `pip install --dry-run --no-deps` against the exact version — uses the same resolver path docker build will, so there's no consistency window. Polls up to 3 min.

### Note
- 0.1.3's runtime image does not exist on GHCR (build failed before pushing). Users should reference `ghcr.io/rovikrobert/cosinabox-runtime:0.1` (floating tag → 0.1.4) or `:0.1.4`/`:0.1.2` explicitly. `:0.1.3` is unavailable.

## [0.1.3] — 2026-04-21

### Changed
- User-repo template `Dockerfile` now uses `FROM ghcr.io/rovikrobert/cosinabox-runtime:0.1` (the runtime base image published alongside the engine since 0.1.2). Scaffolded Docker builds drop from ~60–90s to ~7s because Python 3.11 + `cosinabox[google]` are preinstalled; extras (e.g. `[attio]`) layer on top. The template flip landed on main *after* 0.1.2 was tagged, so this release is needed to propagate the new template to PyPI consumers of `cosinabox init`.

## [0.1.2] — 2026-04-21

### Added
- `cosinabox init` now writes `.cosinabox-version` containing the scaffolding engine version — future `doctor`/`describe`/`migrate` commands can surface drift between scaffold and current install.
- `cosinabox init` rewrites the scaffolded `pyproject.toml` dep pin to match the scaffolding engine's major.minor range (e.g. engine 0.2.x → `cosinabox[google]>=0.2,<0.3`). Kills the footgun where the template's hardcoded `>=0.1,<0.2` broke scaffolding after a minor bump.
- Release workflow now builds a multi-arch (amd64 + arm64) runtime image and pushes it to `ghcr.io/rovikrobert/cosinabox-runtime:{version,major.minor,latest}` on every non-prerelease tag. User-repos can opt into `FROM ghcr.io/rovikrobert/cosinabox-runtime:0.1` for faster builds.

## [0.1.1] — 2026-04-20

### Fixed
- Google OAuth refresh no longer over-requests scopes. `build_credentials` and `build_all_credentials` stopped passing `scopes=` on `Credentials()`, which was causing `invalid_scope: Bad Request` on refresh for tokens minted before `drive.readonly` was added to `GOOGLE_DEFAULT_SCOPES`. Gmail + Calendar reads now keep working on pre-Drive refresh tokens; Drive API calls 403 for those tokens (DriveTool catches it) until the user re-mints via `cosinabox auth google`.

## [0.1.0] — 2026-04-21

Initial public release.

### Added
- Core `App` orchestrator — config loader, job scheduler, Telegram bot, agent loop.
- Five built-in jobs: morning briefing, pre-meeting prep, evening wrap, weekly review, follow-up nudges.
- Google integration (optional extra `[google]`): Calendar + Gmail tools, OAuth flow.
- Attio integration (optional extra `[attio]`): stakeholder CRM sync, keep-warm reminders.
- Fireflies integration (optional extra `[fireflies]`): meeting transcript ingest for post-meeting debrief.
- Web search tool: Anthropic-managed server tool (no external API key required).
- Persona templates (one ships: `founder`).
- Setup interview state machine via `cosinabox init`.
- JSON Schemas for `personality.md`, `stakeholders.yaml`, `jobs.yaml`, `integrations.yaml`.
- `cosinabox validate` / `simulate` / `migrate` commands.
- Commitment tracking with auto-resolve verification (Gmail + Fireflies evidence).
- Auth-health watcher for revoked Google tokens.
- Model-chain failover for Anthropic 429/529 responses.

[0.1.0]: https://github.com/rovikrobert/cosinabox/releases/tag/v0.1.0
