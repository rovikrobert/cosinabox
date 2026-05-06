# Changelog

All notable changes to cosinabox will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- Serper integration (optional extra `[search]`): web search tool.
- Persona templates (one ships: `founder`).
- Setup interview state machine via `cosinabox init`.
- JSON Schemas for `personality.md`, `stakeholders.yaml`, `jobs.yaml`, `integrations.yaml`.
- `cosinabox validate` / `simulate` / `migrate` commands.
- Commitment tracking with auto-resolve verification (Gmail + Fireflies evidence).
- Auth-health watcher for revoked Google tokens.
- Model-chain failover for Anthropic 429/529 responses.

[0.1.0]: https://github.com/rovikrobert/cosinabox/releases/tag/v0.1.0
