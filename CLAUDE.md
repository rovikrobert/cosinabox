# CLAUDE.md — cosinabox engine repository

Welcome. This file orients Claude Code (and similar AI coding agents) to the cosinabox engine repo. It is **not** for agents working on a user's CoSinaBox instance — that file is `src/cosinabox/templates/user-repo/CLAUDE.md`.

If you are a Claude Code session starting work on this repo, read this file fully before any file edit. It is loaded into your context automatically by the harness.

## What this repo is

cosinabox is the engine for an open-source Chief of Staff agent. It ships as:

- A Python package (`cosinabox` on PyPI)
- A Docker base image (`cosinabox/runtime:0.1.x`)
- A user-repo template that's scaffolded by `cosinabox init`

The engine is opinionated about being a Chief of Staff. See `docs/specs/2026-04-11-cosinabox-design.md` for the full design and the v0.1 scope.

## Cutover context

The primary maintainer is migrating a legacy private Chief of Staff implementation onto cosinabox. New CoS features should default to this engine. External contributors can ignore this — the engine is self-contained and every feature here is meant for OSS users. The migration plan itself lives in the maintainer's private repo, not here.

## Project structure

```
cosinabox/
├── src/cosinabox/
│   ├── app/                # App orchestrator (split into config, tools, jobs, alerts, chat)
│   ├── agent/              # Claude API loop, routing, cost tracking
│   ├── bot/                # Telegram adapter (only channel in v0.1)
│   ├── memory/             # SQLite layer
│   ├── scheduler/          # APScheduler integration
│   ├── jobs/               # 5 built-in jobs
│   ├── tools/              # External integrations (Google, Fireflies, Serper)
│   ├── prompts/            # Default prompt templates with {{personality}} slots
│   ├── personas/           # Persona templates (one ships in v0.1: founder)
│   ├── interview/          # Setup interview state machine
│   ├── cli/                # CLI commands
│   ├── schemas/            # JSON Schemas for user config files
│   ├── defaults.py         # All encoded operational defaults
│   └── templates/user-repo/  # Scaffold copied by `cosinabox init`
├── tests/
├── docs/
│   ├── retros/             # One retro per completed plan
│   └── discipline/         # Engine-side discipline doc
├── pyproject.toml
├── .pre-commit-config.yaml
├── .github/workflows/      # CI: test, lint, type-check, release
└── CLAUDE.md (this file)
```

## Safety rules (non-negotiable)

These are absolute. No exceptions.

1. **Worktree at session start.** Every session that edits files must be inside a git worktree under `~/.worktrees/cosinabox/<branch>`. The repo's `.claude/settings.json` runs a SessionStart hook that warns if you're not. Read it.

2. **No bypassing pre-commit hooks.** `git commit --no-verify` is forbidden unless the user explicitly asks for it in this session. Pre-commit runs ruff + mypy + pytest + secret scan. If a check fails, fix the underlying issue.

3. **No secrets in tracked files.** API keys, OAuth tokens, and credentials live only in `.env` (gitignored) or in CI environment secrets. The pre-commit secret scan blocks accidents.

4. **Never edit `src/cosinabox/templates/user-repo/CLAUDE.md` to test something.** That file is the canonical user-repo CLAUDE.md template — every `cosinabox init` user gets a copy. Test changes in a scratch user repo, not in the template.

5. **Never break the schema_version contract.** User repos pin a cosinabox version. If you change the JSON Schema for any user-facing config file (`personality.md`, `stakeholders.yaml`, `jobs.yaml`, `integrations.yaml`), bump the schema version and write a `cosinabox migrate` migration in the same PR.

6. **Per-task git commit, per-milestone PR, per-plan retro.** Each task in the active plan gets its own commit. Each milestone closes with a PR (auto-merged after CI). Each completed plan gets a retro in `docs/retros/`. See engine `docs/discipline/` for details.

## Quality rules

These are strong defaults. Breaking them requires a one-line justification in the commit message.

1. **TDD: red-green-commit.** Write the failing test first. Run it to confirm it fails. Implement the minimal code to make it pass. Run it to confirm it passes. Commit. The writing-plans skill prescribes this; the engine repo enforces it.

2. **Tests are foreground.** Run `pytest` directly. Never `pytest &` then poll. The cosinabox suite is fast (target: <30s); polling wastes wall-clock and breaks flow. See feedback memory `feedback_test_run_speed.md`.

3. **Defaults live in `defaults.py`.** Every encoded operational default (cost cap, threshold, schedule, retention period) lives in `src/cosinabox/defaults.py` with a comment explaining *why* and the date it was chosen. No magic numbers in business logic.

4. **No personal data in tests.** Tests use generic fixtures (`tests/fixtures/sample/`). Never use real stakeholder names, real meeting titles, or real email content. If a test needs realistic data, generate it.

5. **Optional integrations are optional dependencies.** Anything beyond Anthropic + Telegram + Google goes in an extras group in `pyproject.toml` (`[fireflies]`, `[search]`, etc.). The engine must run with only the core install.

6. **Graceful degradation.** Every job must handle "tool not configured" without crashing. If `fireflies` isn't installed, `morning_briefing` runs without the meeting transcript section, not with a stack trace.

## Workflow rules

1. **Read the active plan first.** Every session that's executing a plan starts by reading the plan from `docs/plans/`, finding the next unchecked task, and starting there. Do not re-read prior conversation transcripts. The plan is the source of truth.

2. **Estimate every task.** When writing or executing a plan, each task has an estimate (5 min / 30 min / 2 hr / 1 day). When a task overshoots by 2x or more, note the overshoot in the milestone retro.

3. **Brainstorm-first for non-trivial design changes.** If a task in the plan turns out to need a design change, STOP execution, invoke the brainstorming skill, update the spec, update the plan, then resume. No silent drift.

4. **End-of-session ritual.** Every session that touched code ends with: pytest (foreground), ruff, mypy, commit, push, PR (with `--auto`), memory note for any new lesson, cleanup of stale branches/worktrees.

5. **PRs are auto-merged with `--auto` flag.** `gh pr create ... && gh pr merge --auto --squash`. Avoids race conditions with concurrent sessions. See feedback memory `feedback_auto_merge.md`.

## OSS-user perspective (mandatory for all edits)

Every line of code, config, and documentation in this engine will be read by someone who didn't write it. Adopt the perspective of a founder who just ran `cosinabox init` and is setting up their CoS for the first time via Claude Code.

1. **No hardcoded names, orgs, or domains.** Descriptions, prompts, and tool schemas must be generic. "Search emails matching a query" not "Search the user's Gmail for Acme invoices." If you see a hardcoded name in a schema or prompt, fix it.

2. **Every capability must be discoverable.** If a feature exists but can only be found by reading source code, it doesn't exist for OSS users. Agent-facing docs (`docs/agent/`) are the discovery surface — update them when adding or changing features.

3. **Show tradeoffs, not just switches.** When a feature is optional, the user needs to know what they gain by enabling it AND what they lose by not enabling it. A toggle with no explanation is a dark pattern.

4. **Fallbacks must be explicit.** If integration X is disabled, the system must either (a) work without it and explain the fallback, or (b) tell the user clearly what's degraded. Silent degradation is a bug.

5. **Configuration is a conversation.** Users interact with config through Claude Code, not by editing YAML directly. Agent-facing docs, `describe` output, and error messages are the UX — treat them as first-class code.

6. **Defaults must be safe for strangers.** Every default in `defaults.py` should make sense for someone you've never met. If a default only makes sense for a specific user, it belongs in user config, not in the engine.

7. **The template is the first impression.** `cosinabox init` output is the first thing users see. Every file in `src/cosinabox/templates/user-repo/` should be self-explanatory with inline comments. If a user needs to read docs to understand the template, the template is incomplete.

## Proactive suggestions (things to watch for and surface)

These aren't rules — they're patterns the agent should notice and surface to the maintainer without being asked.

1. **A task is taking too long.** If you've been on Task N for >2x the estimate, surface the overshoot and ask whether to continue, defer, or revise the task.

2. **A test is flaky.** If a test passes locally but fails in CI (or vice versa), don't retry — investigate. Flaky tests are a quality regression to fix immediately, not paper over.

3. **A schema change is creeping in.** If a PR modifies a JSON Schema or any field in the user-facing config files, the PR must include a migration. If it doesn't, surface the gap before committing.

4. **A defaults.py value is being overridden in business logic.** If you see `if cost > 0.75:` instead of `if cost > defaults.COST_PER_MESSAGE_CAP_USD:`, fix it. Magic numbers are a leak of operational defaults.

5. **A test imports personal data.** If a test references any specific real-world name, company, or stakeholder, surface it — the engine should be generic.

6. **The plan is drifting.** If the current commit touches files that aren't mentioned in any task of the active plan, surface the drift and ask whether to pause and update the plan.

## How to run things

```bash
# Install for development
git clone <repo>
cd cosinabox
git worktree add ~/.worktrees/cosinabox/<branch> -b <branch>
cd ~/.worktrees/cosinabox/<branch>
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,google]"
pre-commit install

# Run tests
pytest                  # full suite, foreground
pytest tests/unit/      # just unit tests
pytest -k cost          # filter by name

# Lint + type check
ruff check src tests
ruff format src tests
mypy src/cosinabox

# CLI smoke test
cosinabox --help
cosinabox init /tmp/test-cos
cosinabox -C /tmp/test-cos validate
cosinabox -C /tmp/test-cos simulate morning_briefing --fixture=sample

# End-of-session ritual (when this script exists)
./scripts/session-end.sh
```

## Active plan

The currently-executing plan is referenced in `docs/active-plan.md` (a one-line file that points at the current plan markdown). Keep this updated when starting and finishing plans.

## Related

- **Spec:** `docs/specs/2026-04-11-cosinabox-design.md`
- **Plan 1:** `docs/plans/2026-04-11-cosinabox-engine-mvp.md`
- **Engine-side discipline doc:** `docs/discipline/cosinabox-development-discipline.md`
- **User-repo CLAUDE.md template:** `src/cosinabox/templates/user-repo/CLAUDE.md` (the canonical template that every `cosinabox init` user receives)

## What's next

If you're a fresh session and the plan says "execute the next unchecked task," go to `docs/active-plan.md`, follow the link, find the next `- [ ]` checkbox, and start there. If anything in this CLAUDE.md is unclear or contradicts the plan, surface the contradiction to the maintainer before proceeding — don't guess.
