# Plan 1 Retro — CoSinaBox Engine MVP

**Date:** 2026-04-12
**Scope:** Milestones 1-4 (engine extraction through CLI + doctor)
**Planned:** ~40 hours across 4 milestones, 47+ tasks
**Actual:** Completed in 3 sessions (M1, M2, M3+M4)

---

## What shipped

Every "Done when" criterion from the plan is met:

| Milestone | Done-when criterion | Status |
|-----------|-------------------|--------|
| M1 | `pytest` passes, imports work, ruff/mypy green | Shipped (PR #2) |
| M2 | `cosinabox simulate morning_briefing` produces output against sample fixture; all tests pass | Shipped (PR #3) |
| M3 | `cosinabox init /tmp/test && cosinabox -C /tmp/test validate` exits 0; pre-commit hook blocks bad commits | Shipped (PR #4) |
| M4 | All CLI commands exist with tests; interview state machine works e2e; doctor checks fire correctly | Shipped (PR #4) |

### Final test count: 109

- M1: 28 tests (memory, cost, routing, loop, bot, tools, prompts, schemas)
- M2: 34 tests (defaults, jobs, scheduler, personas, fixtures, validate, simulate)
- M3: 7 tests (CLAUDE.md size/subdocs, init, pre-commit hook)
- M4: 40 tests (describe, add-stakeholder, set-job-schedule, enable/disable-job, set-persona, migrate, upgrade-docs, auth google, interview, doctor checks x10, doctor CLI, JSON audit, e2e)

### Deliverables inventory

**Engine modules (M1):** agent loop, routing, cost tracker, summarization, memory (SQLite), Telegram bot adapter, Google auth/Gmail/Calendar tools, Fireflies tool, web search tool, prompt templates

**Engine runtime (M2):** defaults.py (all magic numbers), APScheduler integration, 5 built-in jobs (morning_briefing, evening_wrap, pre_meeting_prep, weekly_review, followup_reminder), founder persona, sample fixture, JSON schemas (4), validate command, simulate command

**User-repo template (M3):** 4 config stubs, pyproject/Dockerfile/main.py/.gitignore, CLAUDE.md (<200 lines), 6 agent sub-docs, BEST_PRACTICES.md, pre-commit hook (validate + secret scan), schema reference copies, `cosinabox init`

**CLI + interview + doctor (M4):** 12 CLI commands (describe, add-stakeholder, set-job-schedule, enable-job, disable-job, set-persona, migrate, upgrade-docs, auth google, interview, test, doctor), 10-step interview state machine with JSON persistence, 10 doctor health checks, --json on all read commands

---

## Estimate calibration

The plan estimated ~40 hours total. M3+M4 were completed in a single session using subagent-driven development, which dramatically compressed wall-clock time. Task-level observations:

- **Template/doc tasks (T3.1-T3.12):** Overestimated. These are copy-paste from the plan with no design decisions. The plan budgeted ~12 hours; actual was closer to 2-3 hours of agent time.
- **CLI commands (T4.1-T4.8, T4.10-T4.11):** Accurately estimated. Each follows the same Click pattern — test, implement, register, commit. No surprises.
- **Interview state machine (T4.9):** Accurately estimated. The 10-step design was fully specified in the plan; implementation was mechanical.
- **Doctor checks (T4.12-T4.16):** Slightly overestimated. The Check ABC + registry pattern means each new check is ~20 lines.

**Lesson:** Plans with pseudocode and test templates execute much faster than plans with prose descriptions. The investment in plan detail paid off.

---

## Discipline commitments

| Commitment | Followed? | Notes |
|-----------|-----------|-------|
| Worktree at session start | Yes | `~/.worktrees/cosinabox/m3-m4-user-repo-cli` |
| Per-task commits | Mostly | Some tasks batched (T4.12-T4.15 in one commit) for efficiency |
| Tests before code | Mixed | Subagents wrote tests and code together; plan specified TDD but parallel execution made strict red-green impractical |
| ruff + mypy clean | Yes | Fixed after implementation; caught 58 ruff + 13 mypy issues in cleanup pass |
| PR with --auto | Yes | PR #4 created with auto-merge |
| Retro after milestone | Yes | This document |

**Violation worth noting:** The plan specifies strict TDD (write failing test, then implement). Subagent-driven development wrote tests and implementation together to maximize parallelism. Tests still verified the right behavior, but the red-green discipline was relaxed. For Plan 2, consider whether TDD enforcement at the subagent level matters or if "tests exist and pass" is sufficient.

---

## Lessons learned

1. **Subagent batching is powerful but needs lint passes.** Dispatching 8 subagents in parallel completed T3.3-T3.10 in ~2 minutes, but produced 58 ruff errors and 13 mypy issues. A post-batch lint/format pass should be standard.

2. **Plan detail = execution speed.** Tasks with full pseudocode, test templates, and commit messages executed 3-5x faster than tasks with only prose descriptions. The M3/M4 plan was the most detailed and executed the fastest.

3. **Template files are boring but critical.** The 6 agent sub-docs and BEST_PRACTICES.md are the user's first impression of cosinabox. They shipped verbatim from the plan — no iteration needed because the plan author had already iterated.

4. **Doctor checks compound.** Writing 10 checks felt tedious, but the registry pattern makes each one ~20 lines. The real value is the `cosinabox doctor --json` contract — agents can parse it programmatically.

5. **Interview state machine is the riskiest piece.** The 10-step flow works for canned answers, but real users will give ambiguous input ("my timezone is Pacific" vs "America/Los_Angeles"). Plan 2 should stress-test with realistic user input.

---

## Decisions for Plan 2

Plan 2 is the `rovik-keevs` migration: build the private user repo, migrate cos-agent data, parallel run, cutover.

### Questions to resolve in Plan 2 brainstorming

1. **Schema bumps:** v0.1 schema_version is 1 everywhere. If rovik-keevs needs fields cos-agent doesn't have (e.g., Telegram chat_id in integrations.yaml), does that warrant a schema_version bump or just optional fields?

2. **cos-agent SQLite copier:** The plan deferred `cosinabox migrate-from cos-agent` to Plan 2. What data needs to migrate? (conversation history, cost logs, follow-up state)

3. **Parallel run strategy:** How long should cosinabox run alongside cos-agent before cutover? What's the success criterion? (e.g., "morning_briefing matches cos-agent output for 5 consecutive days")

4. **Memory service integration:** cos-agent uses an external memory service (Railway-deployed). Does cosinabox's SQLite layer replace it, or does it need a memory service adapter?

5. **New doctor checks:** Should Plan 2 add checks specific to migration? (e.g., `cos_agent_data_stale` — migration ran but hasn't been refreshed in >7 days)

---

## Summary

Plan 1 shipped everything it set out to ship. The cosinabox engine compiles, tests pass, the CLI works end-to-end, and `cosinabox init` produces a usable scaffold. The next step is Plan 2: migrate rovik-keevs from cos-agent to cosinabox.
