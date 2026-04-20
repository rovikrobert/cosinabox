# Changelog

All notable changes to cosinabox will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
