# Changelog

All notable changes to cosinabox will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
