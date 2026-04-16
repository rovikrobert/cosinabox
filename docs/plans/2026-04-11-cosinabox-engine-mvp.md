# CoSinaBox Engine MVP — Plan 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `cosinabox` engine from a fresh repo to a state where (a) all five built-in jobs run end-to-end against a sample fixture, (b) a fresh user repo is scaffoldable via `cosinabox init`, and (c) the full agent-led setup interview + doctor checks work locally. No `rovik-keevs` migration in this plan; no public launch in this plan. Those are Plans 2 and 3.

**Scope:** Spec Milestones 1-4 only:
- **M1** Engine extraction from `cos-agent` (Phase 1 of the spec)
- **M2** Engine first-run with sample fixture (Phase 2 of the spec)
- **M3** User repo template + CLAUDE.md + sub-docs (Section 5 Layer 2-5 of the spec)
- **M4** CLI commands + interview state machine + doctor checks (Section 5 Layer 3-4 + CLI list of the spec)

**Out of scope for Plan 1:** Plans 2 (rovik-keevs migration + parallel run) and 3 (public PyPI/Docker/GitHub launch) ship separately. The `migrate-from cos-agent` SQLite copier is **deferred to Plan 2** because it's only useful once `rovik-keevs` exists.

**Architecture:** Engine + thin user repo. The `cosinabox` package is a Python library + CLI. End-users get a tiny repo (`templates/user-repo/`) that imports the engine and supplies four config files. Built-in jobs run on APScheduler; the Telegram bot is the only outbound channel in v0.1; SQLite is the memory layer; Anthropic Claude is the LLM. Setup is driven by an agent-led interview state machine that the engine owns (not improvised by the agent).

**Tech Stack:** Python 3.11+, Anthropic SDK, python-telegram-bot, APScheduler, SQLite (stdlib), google-api-python-client + google-auth (optional via `[google]` extra), pytest, ruff, mypy, pre-commit, jsonschema (config validation), pyyaml, click (CLI), Jinja2 (prompt templates).

---

## How to resume this plan in a fresh session

If you're a new Claude Code session opening this file with no chat history:

1. **Read this whole plan.** It is the source of truth, not chat context.
2. **Find the next unchecked `- [ ]` box.** Tasks are numbered T1.x and run top-to-bottom inside each milestone.
3. **Confirm you're in a worktree.** `pwd` should be under `~/.worktrees/cosinabox/...` (or `~/.worktrees/cantina/...` for tasks that still touch the Cantina repo). If not, create one before any file edit.
4. **Read the spec only if the plan is unclear** at `docs/superpowers/specs/2026-04-11-cosinabox-design.md`. The plan is meant to be self-contained — if you have to consult the spec to understand a task, that's a plan defect to flag in the milestone retro.
5. **Read the engine-repo CLAUDE.md draft** at `docs/superpowers/plans/2026-04-11-cosinabox-engine-claude-md.md` if working on Task T1.2 (cosinabox repo bootstrap). This draft becomes `cosinabox/CLAUDE.md` in T1.2.
6. **Don't trust prior chat transcripts.** Per discipline commitment 2, future sessions read the plan, not the chat.

---

## Repo layout reference

This plan creates a brand-new public repo `cosinabox/` separate from `Cantina`. The plan is being authored from a Cantina worktree, but **execution of Tasks T1.2 onward happens inside the cosinabox repo**, not Cantina. T1.1 (the inventory) is the only task that runs in Cantina.

When this plan says "create file `X`", interpret the path as relative to the cosinabox repo root unless it explicitly starts with `Cantina/` or `cos-agent/`.

```
cosinabox/                                # new repo, public, AGPL
├── pyproject.toml
├── LICENSE                               # AGPL-3.0
├── README.md                             # written in Plan 3
├── CLAUDE.md                             # T1.2 (content from engine-claude-md draft)
├── AGENTS.md                             # written in Plan 3
├── CONTRIBUTING.md                       # written in Plan 3
├── OUT_OF_SCOPE.md                       # written in Plan 3
├── .pre-commit-config.yaml               # T1.2
├── .gitignore                            # T1.2
├── .github/
│   ├── FUNDING.yml                       # Plan 3
│   └── workflows/test.yml                # T1.2 (CI runs ruff + mypy + pytest + secret scan)
├── docs/
│   ├── discipline/                       # T1.2 (mirrored from Cantina's discipline doc)
│   ├── retros/                           # populated as plans complete
│   ├── superpowers/specs/                # spec lives here once moved (Plan 3)
│   └── superpowers/plans/                # plans live here once moved (Plan 3)
├── src/cosinabox/
│   ├── __init__.py                       # exports App, Job, Tool, Personality
│   ├── app.py                            # T1.2 stub; T2.x fills it in
│   ├── defaults.py                       # T2.1
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── loop.py                       # T1.6 (was cos-agent src/agent.py)
│   │   ├── routing.py                    # T1.5 (was cos-agent src/router.py)
│   │   ├── cost.py                       # T1.4 (was cos-agent src/cost_tracker.py)
│   │   └── summarization.py              # T1.13 (was cos-agent src/agent_summarization.py)
│   ├── bot/
│   │   ├── __init__.py
│   │   └── telegram.py                   # T1.7 (was cos-agent src/bot.py)
│   ├── memory/
│   │   ├── __init__.py
│   │   └── sqlite.py                     # T1.3 (was cos-agent src/memory.py)
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── runner.py                     # T2.2
│   ├── jobs/
│   │   ├── __init__.py
│   │   ├── morning_briefing.py           # T2.3
│   │   ├── evening_wrap.py               # T2.4
│   │   ├── pre_meeting_prep.py           # T2.5
│   │   ├── weekly_review.py              # T2.6
│   │   └── followup_reminder.py          # T2.7
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── google/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                   # T1.8 (was google_auth.py)
│   │   │   ├── gmail.py                  # T1.9 (was gmail_tool.py)
│   │   │   └── calendar.py               # T1.10 (was calendar_tool.py)
│   │   ├── fireflies.py                  # T1.11
│   │   └── web_search.py                 # T1.12
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── core.py                       # T1.13 (was cos-agent src/prompts/core.py)
│   │   └── briefing.py                   # T1.13 (was cos-agent src/prompts/briefing.py)
│   ├── personas/
│   │   └── founder.md                    # T2.8
│   ├── interview/
│   │   ├── __init__.py
│   │   └── state_machine.py              # T4.9
│   ├── schemas/
│   │   ├── personality.schema.json       # T2.10
│   │   ├── stakeholders.schema.json      # T2.10
│   │   ├── jobs.schema.json              # T2.10
│   │   └── integrations.schema.json      # T2.10
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── main.py                       # T1.2 stub; T4.x fills in commands
│   │   ├── init.py                       # T3.13 (cosinabox init)
│   │   ├── validate.py                   # T2.11
│   │   ├── simulate.py                   # T2.13
│   │   ├── describe.py                   # T4.1
│   │   ├── doctor.py                     # T4.20
│   │   ├── interview.py                  # T4.10
│   │   ├── add_stakeholder.py            # T4.2
│   │   ├── set_job_schedule.py           # T4.3
│   │   ├── enable_job.py                 # T4.4
│   │   ├── disable_job.py                # T4.5
│   │   ├── set_persona.py                # T4.6
│   │   ├── migrate.py                    # T4.7
│   │   ├── upgrade_docs.py               # T4.8
│   │   ├── auth_google.py                # T4.11
│   │   └── test_runner.py                # T4.12
│   └── templates/user-repo/              # T3.x lives here (the scaffold)
├── tests/
│   ├── conftest.py                       # T1.2
│   ├── fixtures/sample/                  # T2.9
│   │   ├── calendar_events.json
│   │   ├── emails.json
│   │   └── stakeholders.yaml
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── .claude/
    └── settings.json                     # T1.2 (SessionStart hook for worktree check)
```

---

## T1.1 Inventory: cos-agent file triage

This table is the **output of Task T1.1** (already completed during plan authoring on 2026-04-12 — see T1.1 for the regeneration command). It is reproduced here so subsequent tasks can reference it without re-deriving. Every Python file under `cos-agent/src/`, `cos-agent/tests/`, `cos-agent/scripts/`, and `cos-agent/config/` is classified as one of:

- **EXTRACT** — copy into the cosinabox engine, strip Rovik-specific bits, generalize.
- **DEFER** — does not ship in v0.1. Either becomes a `rovik-keevs/custom_jobs/*.py` in Plan 2, or is deferred to v0.2+ entirely.
- **DROP** — does not survive the migration. Already replaced by something else (e.g., the standalone memory-service), or scope-creep that the spec explicitly excludes.

**Source files** (`cos-agent/src/`):

| File | Disposition | Target / reason |
|---|---|---|
| `src/__init__.py` | DROP | Recreated in cosinabox |
| `src/action_types.py` | DEFER (v0.2) | Tied to commitments + decision memo subsystems |
| `src/agent.py` | EXTRACT | → `src/cosinabox/agent/loop.py` (T1.6); strip Rovik routing rules |
| `src/agent_failover.py` | DROP | Multi-provider failover not in v0.1 scope |
| `src/agent_summarization.py` | EXTRACT | → `src/cosinabox/agent/summarization.py` (T1.13); built-in v0.1 feature (>25 message threshold) |
| `src/analytics.py` | DROP | Cantina-specific analytics; cost tracking lives in `agent/cost.py` |
| `src/anthropic_client.py` | DROP | Thin wrapper; collapses into `agent/loop.py` |
| `src/api.py` | DROP | FastAPI surface not in v0.1 scope |
| `src/auto_resolve.py` | DEFER (v0.2) | Briefing self-resolution feature |
| `src/bot.py` | EXTRACT | → `src/cosinabox/bot/telegram.py` (T1.7); strip dual-account assumptions |
| `src/bot_approval.py` | DEFER (v0.2) | Approval workflow tied to scheduling subsystem |
| `src/bot_commands.py` | EXTRACT (partial) | Generic /help, /status commands → `cosinabox/bot/telegram.py`; Rovik-specific commands DROP |
| `src/bot_queue.py` | DROP | Multi-bot queue not in v0.1 scope |
| `src/bot_scheduling.py` | DEFER (v0.2) | Scheduling subsystem |
| `src/bot_wa_relay.py` | DEFER (v0.2) | WhatsApp multi-channel |
| `src/commitments.py` | DEFER (v0.2) | Commitment tracking subsystem |
| `src/commitments_db.py` | DEFER (v0.2) | Commitment tracking subsystem |
| `src/consult.py` | DROP | Keevs consult API; Cantina-specific |
| `src/cost_tracker.py` | EXTRACT | → `src/cosinabox/agent/cost.py` (T1.4); defaults from Layer 1 |
| `src/decision_memos.py` | DEFER (v0.2) | Decision memo subsystem |
| `src/intel/__init__.py` | DEFER (rovik-keevs) | → `rovik-keevs/custom_jobs/competitive_intel.py` shell |
| `src/intel/collector.py` | DEFER (rovik-keevs) | Asia Lab Tracker |
| `src/intel/synthesizer.py` | DEFER (rovik-keevs) | Asia Lab Tracker |
| `src/interaction_logger.py` | DROP | Subsumed by memory-service |
| `src/interfaces/__init__.py` | DROP | Multi-channel adapters not in v0.1 |
| `src/interfaces/gmail_interface.py` | DEFER (v0.2) | Gmail webhook receiver (Pub/Sub) |
| `src/interfaces/google_webhooks.py` | DEFER (v0.2) | Webhook adapter |
| `src/interfaces/whatsapp_interface.py` | DEFER (v0.2) | WhatsApp |
| `src/interfaces/whatsapp_relay.py` | DEFER (v0.2) | WhatsApp |
| `src/lesson_extractor.py` | DROP | Lessons live in agent memory now |
| `src/memory.py` | EXTRACT | → `src/cosinabox/memory/sqlite.py` (T1.3); schema unchanged |
| `src/memory_service.py` | DROP | Standalone Railway service; not bundled |
| `src/memory_tracking.py` | DROP | Standalone memory-service |
| `src/policy.py` | DROP | Cantina policy gates |
| `src/prompts/__init__.py` | EXTRACT | → `src/cosinabox/prompts/__init__.py` (T1.13) |
| `src/prompts/briefing.py` | EXTRACT | → `src/cosinabox/prompts/briefing.py` (T1.13); replace hardcoded names with `{{personality}}` slots |
| `src/prompts/core.py` | EXTRACT | → `src/cosinabox/prompts/core.py` (T1.13) |
| `src/prompts/mira.py` | DEFER (rovik-keevs) | → `rovik-keevs/custom_jobs/weekly_synthesis.py` shell |
| `src/prompts/modules.py` | EXTRACT (partial) | Generic prompt-module composer → `cosinabox/prompts/modules.py`; persona-specific modules DROP |
| `src/prompts/rela.py` | DEFER (rovik-keevs) | → `rovik-keevs/custom_jobs/vip_relationship.py` shell |
| `src/router.py` | EXTRACT | → `src/cosinabox/agent/routing.py` (T1.5); default rules; user can override |
| `src/scheduler/__init__.py` | EXTRACT | → `src/cosinabox/scheduler/__init__.py` (T2.2) |
| `src/scheduler/briefing_pipeline.py` | EXTRACT | → folded into `src/cosinabox/jobs/morning_briefing.py` (T2.3) |
| `src/scheduler/extraction_jobs.py` | DROP | Memory-service subsumes this |
| `src/scheduler/helpers.py` | EXTRACT | → `src/cosinabox/scheduler/helpers.py` (T2.2); generic schedule helpers only |
| `src/scheduler/intel_jobs.py` | DEFER (rovik-keevs) | Asia Lab Tracker scheduling |
| `src/scheduler/jobs.py` | EXTRACT (partial) | Generic job-base class → `cosinabox/jobs/base.py` (T2.2); the 5 core jobs go to `cosinabox/jobs/*.py` (T2.3-T2.7) |
| `src/scheduler/lifecycle.py` | EXTRACT | → `src/cosinabox/scheduler/lifecycle.py` (T2.2); start/stop hooks |
| `src/scheduler/queue.py` | DROP | Multi-bot queue |
| `src/scheduler/scheduling_jobs.py` | DEFER (v0.2) | Scheduling subsystem |
| `src/scheduling/__init__.py` | DEFER (v0.2) | Meeting scheduling subsystem (entire package) |
| `src/scheduling/backchannel.py` | DEFER (v0.2) | Scheduling subsystem |
| `src/scheduling/coordinator.py` | DEFER (v0.2) | Scheduling subsystem |
| `src/scheduling/db.py` | DEFER (v0.2) | Scheduling subsystem |
| `src/scheduling/models.py` | DEFER (v0.2) | Scheduling subsystem |
| `src/scheduling/outreach.py` | DEFER (v0.2) | Scheduling subsystem |
| `src/scheduling/participant.py` | DEFER (v0.2) | Scheduling subsystem |
| `src/scheduling/response_parser.py` | DEFER (v0.2) | Scheduling subsystem |
| `src/scheduling/slot_scorer.py` | DEFER (v0.2) | Scheduling subsystem |
| `src/server.py` | DROP | FastAPI server |
| `src/sub_agent.py` | DROP | Sub-agent dispatch not in v0.1 |
| `src/subagent.py` | DROP | Duplicate of `sub_agent.py` |
| `src/tools/__init__.py` | EXTRACT | → `src/cosinabox/tools/__init__.py` (T1.8) |
| `src/tools/airtable_tool.py` | DROP | Not used |
| `src/tools/attio_client.py` | DEFER (rovik-keevs) | → `rovik-keevs/custom_jobs/attio_sync.py` |
| `src/tools/attio_tool.py` | DEFER (rovik-keevs) | → `rovik-keevs/custom_jobs/attio_sync.py` |
| `src/tools/auth_context.py` | EXTRACT | → folded into `src/cosinabox/tools/google/auth.py` (T1.8); single-account assumption |
| `src/tools/calendar_tool.py` | EXTRACT | → `src/cosinabox/tools/google/calendar.py` (T1.10); keep conflict detection |
| `src/tools/calendar_write.py` | EXTRACT | → folded into `src/cosinabox/tools/google/calendar.py` (T1.10) |
| `src/tools/commitment_tool.py` | DEFER (v0.2) | Commitment subsystem |
| `src/tools/decision_memo_tool.py` | DEFER (v0.2) | Decision memo subsystem |
| `src/tools/drive_tool.py` | DEFER (v0.2) | Drive integration |
| `src/tools/email_delegate_tool.py` | DEFER (v0.2) | Delegate email send |
| `src/tools/fireflies_tool.py` | EXTRACT | → `src/cosinabox/tools/fireflies.py` (T1.11); optional dep |
| `src/tools/gmail_helpers.py` | EXTRACT | → folded into `src/cosinabox/tools/google/gmail.py` (T1.9) |
| `src/tools/gmail_tool.py` | EXTRACT | → `src/cosinabox/tools/google/gmail.py` (T1.9); single-account default |
| `src/tools/google_auth.py` | EXTRACT | → `src/cosinabox/tools/google/auth.py` (T1.8); single-account default |
| `src/tools/link_tool.py` | DROP | Niche utility |
| `src/tools/memory_tool.py` | DROP | Memory access via memory-service, not a tool |
| `src/tools/rss_tool.py` | DEFER (v0.2) | Generic RSS reader; out of scope |
| `src/tools/scheduling_tool.py` | DEFER (v0.2) | Scheduling subsystem |
| `src/tools/sheets_tool.py` | DROP | Not used |
| `src/tools/vector_search_tool.py` | DROP | Memory-service handles vector search |
| `src/tools/web_search_tool.py` | EXTRACT | → `src/cosinabox/tools/web_search.py` (T1.12); optional dep |
| `src/webhook_worker.py` | DEFER (v0.2) | Webhook processing |

**Test files** (`cos-agent/tests/`):

| File | Disposition | Target / reason |
|---|---|---|
| `tests/conftest.py` | EXTRACT | → `tests/conftest.py` (T1.2); rewrite to use generic fixtures |
| `tests/test_agent.py` | EXTRACT | → `tests/unit/test_agent_loop.py` (T1.6); strip Rovik fixture data |
| `tests/test_agent_api.py` | EXTRACT | → `tests/unit/test_agent_loop.py` (T1.6) |
| `tests/test_agent_budget.py` | EXTRACT | → `tests/unit/test_cost.py` (T1.4) |
| `tests/test_agent_memory.py` | EXTRACT | → `tests/unit/test_memory.py` (T1.3) |
| `tests/test_analytics.py` | DROP | Analytics dropped |
| `tests/test_api.py` | DROP | API dropped |
| `tests/test_ask_agent.py` | EXTRACT | → `tests/integration/test_agent_loop.py` (T1.6) |
| `tests/test_attio.py` | DEFER (rovik-keevs) | Attio in custom_jobs |
| `tests/test_auto_resolve.py` | DEFER (v0.2) | Auto-resolve dropped |
| `tests/test_bot.py` | EXTRACT | → `tests/unit/test_bot_telegram.py` (T1.7) |
| `tests/test_bot_wa_relay.py` | DEFER (v0.2) | WhatsApp |
| `tests/test_briefing_id_sanitization.py` | EXTRACT | → `tests/unit/test_jobs_morning_briefing.py` (T2.3) |
| `tests/test_calendar_tool.py` | EXTRACT | → `tests/unit/test_google_calendar.py` (T1.10) |
| `tests/test_commitments.py` | DEFER (v0.2) | Commitments dropped |
| `tests/test_commitments_db.py` | DEFER (v0.2) | Commitments dropped |
| `tests/test_consult.py` | DROP | Consult dropped |
| `tests/test_cost_tracker.py` | EXTRACT | → `tests/unit/test_cost.py` (T1.4) |
| `tests/test_dashboard.py` | DROP | Cantina dashboard |
| `tests/test_decision_memos.py` | DEFER (v0.2) | Decision memos dropped |
| `tests/test_digest_formatting.py` | EXTRACT | → `tests/unit/test_jobs_morning_briefing.py` (T2.3) |
| `tests/test_drive_tool.py` | DEFER (v0.2) | Drive dropped |
| `tests/test_eval.py` | DROP | Internal eval harness |
| `tests/test_extraction_jobs.py` | DROP | Memory-service subsumes |
| `tests/test_fireflies_dates.py` | EXTRACT | → `tests/unit/test_fireflies.py` (T1.11) |
| `tests/test_fireflies_format.py` | EXTRACT | → `tests/unit/test_fireflies.py` (T1.11) |
| `tests/test_gmail_interface.py` | DEFER (v0.2) | Webhook interface |
| `tests/test_gmail_tool.py` | EXTRACT | → `tests/unit/test_google_gmail.py` (T1.9) |
| `tests/test_google_auth.py` | EXTRACT | → `tests/unit/test_google_auth.py` (T1.8) |
| `tests/test_google_webhooks.py` | DEFER (v0.2) | Webhooks |
| `tests/test_intel_collector.py` | DEFER (rovik-keevs) | Asia Lab Tracker |
| `tests/test_intel_synthesizer.py` | DEFER (rovik-keevs) | Asia Lab Tracker |
| `tests/test_job_failures.py` | EXTRACT | → `tests/integration/test_scheduler.py` (T2.2); generic job error path |
| `tests/test_lesson_extractor.py` | DROP | Lesson extractor dropped |
| `tests/test_memory.py` | EXTRACT | → `tests/unit/test_memory.py` (T1.3) |
| `tests/test_memory_commands.py` | DROP | Memory command surface dropped |
| `tests/test_memory_service.py` | DROP | Memory-service standalone |
| `tests/test_migration.py` | DROP | Memory migration; not relevant |
| `tests/test_mira.py` | DEFER (rovik-keevs) | Mira → custom_jobs |
| `tests/test_person_recall.py` | DROP | Memory-service domain |
| `tests/test_phase2.py` | DROP | Cos-agent's old phase 2 |
| `tests/test_policy.py` | DROP | Policy dropped |
| `tests/test_prompt_caching.py` | EXTRACT | → `tests/integration/test_agent_loop.py` (T1.6) |
| `tests/test_prompts.py` | EXTRACT | → `tests/unit/test_prompts.py` (T1.13) |
| `tests/test_rela.py` | DEFER (rovik-keevs) | Rela → custom_jobs |
| `tests/test_router.py` | EXTRACT | → `tests/unit/test_routing.py` (T1.5) |
| `tests/test_scheduler.py` | EXTRACT | → `tests/unit/test_scheduler.py` (T2.2) |
| `tests/test_scheduler_integration.py` | EXTRACT | → `tests/integration/test_scheduler.py` (T2.2) |
| `tests/test_scheduling.py` | DEFER (v0.2) | Scheduling subsystem |
| `tests/test_self_resolution.py` | DEFER (v0.2) | Auto-resolve |
| `tests/test_subagent.py` | DROP | Sub-agent dropped |
| `tests/test_triage_fixes.py` | DROP | Cos-agent-specific bug fix tests |
| `tests/test_webhook_worker.py` | DEFER (v0.2) | Webhooks |
| `tests/test_whatsapp_interface.py` | DEFER (v0.2) | WhatsApp |
| `tests/test_whatsapp_relay.py` | DEFER (v0.2) | WhatsApp |

**Config + scripts** (`cos-agent/config/`, `cos-agent/scripts/`):

| File | Disposition | Target / reason |
|---|---|---|
| `config/asia_lab_targets.py` | DEFER (rovik-keevs) | Asia Lab Tracker config |
| `config/schema.sql` | EXTRACT | → folded into `src/cosinabox/memory/sqlite.py` schema (T1.3) |
| `config/settings.py` | EXTRACT (partial) | Generic config-loading helpers → `cosinabox/app.py`; Rovik-specific values DROP |
| `config/standing_orders.py` | DROP | Cantina-specific standing orders; replaced by `personality.md` |
| `config/tool_subsets.py` | EXTRACT | → folded into `cosinabox/agent/routing.py` (T1.5) |
| `scripts/backfill_linkedin.py` | DROP | One-shot Cantina script |
| `scripts/find_duplicate_commitments.py` | DEFER (v0.2) | Commitments |
| `scripts/merge_duplicate_commitments.py` | DEFER (v0.2) | Commitments |
| `scripts/migrate_commitments_to_pg.py` | DROP | Postgres migration; commitments deferred |
| `scripts/migrate_cos_state.py` | DROP | One-shot migration done |
| `scripts/migrate_crm_to_attio.py` | DEFER (rovik-keevs) | Attio in custom_jobs |
| `scripts/pre_merge_check.py` | DROP | Cantina-specific |
| `scripts/setup_oauth.py` | EXTRACT | → `src/cosinabox/cli/auth_google.py` (T4.11); generalize |

**Triage summary:** ~33 EXTRACT, ~30 DEFER, ~26 DROP. The EXTRACT set is small enough to fit in M1; the DEFER set goes into Plan 2 (rovik-keevs) or v0.2 backlog; the DROP set is gone.

---

## Milestone 1 — Engine extraction

**Goal:** A bare `cosinabox` repo whose modules compile, whose unit tests pass, and whose ported components (memory, cost, router, agent loop, bot adapter, Google tools, Fireflies, web search, prompts) work in isolation. No `App.run()` yet — that lands in M2.

**Done when:**
- `cosinabox` repo exists with `pyproject.toml`, CI, pre-commit, CLAUDE.md, discipline doc.
- `pytest` passes inside the cosinabox repo (unit + integration tests for all M1 components).
- `from cosinabox.agent.loop import AgentLoop` and the other ported imports succeed.
- `ruff check src tests` and `mypy src/cosinabox` pass.

**PR title:** `Plan 1 Milestone 1: engine extraction`
**PR exit criteria:** All M1 tasks checked, CI green, reviewer (or self-review) approves.

---

### Task T1.1: Inventory cos-agent and produce triage table

**Est:** 1 hr (already done during plan authoring on 2026-04-12)

**Files:**
- Create: `Cantina/docs/superpowers/plans/2026-04-11-cosinabox-engine-mvp.md` (this plan, contains the triage)

This task is **complete** as a side-effect of plan authoring — the triage table above ("T1.1 Inventory") is the deliverable. If you are re-running this task in a fresh session because the cos-agent file set has changed, regenerate the table with the commands below.

- [x] **Step 1: List every cos-agent Python source file**

```bash
cd /Users/rovikrobert/Cantina/cos-agent
find src -type f -name '*.py' | sort
find tests -type f -name '*.py' | sort
find scripts config -type f \( -name '*.py' -o -name '*.sql' \) | sort
```

- [x] **Step 2: For each file, decide EXTRACT / DEFER / DROP**

Apply this rule: *"Would I include this if I were starting cosinabox fresh, given the v0.1 spec?"* If yes → EXTRACT. If no but it's preserved as a custom_jobs shell or v0.2 candidate → DEFER. If no and it's gone for good → DROP.

- [x] **Step 3: Write the triage table into this plan under "T1.1 Inventory"**

(Done — see the table above.)

- [x] **Step 4: Commit**

```bash
cd ~/.worktrees/cantina/docs-cosinabox-plan-1
git add docs/superpowers/plans/2026-04-11-cosinabox-engine-mvp.md
git commit -m "docs(plan): cosinabox engine MVP Plan 1 — triage + outline (Plan 1, Task T1.1)"
```

---

### Task T1.2: Bootstrap the cosinabox repo

**Est:** 2 hr

**Files (all NEW, in the new `cosinabox/` repo, NOT Cantina):**
- Create: `cosinabox/pyproject.toml`
- Create: `cosinabox/LICENSE` (AGPL-3.0 standard text)
- Create: `cosinabox/.gitignore`
- Create: `cosinabox/.pre-commit-config.yaml`
- Create: `cosinabox/.github/workflows/test.yml`
- Create: `cosinabox/CLAUDE.md` (copy from `Cantina/docs/superpowers/plans/2026-04-11-cosinabox-engine-claude-md.md` content below the "---" front-matter line)
- Create: `cosinabox/docs/discipline/cosinabox-development-discipline.md` (mirror of `Cantina/docs/discipline/cosinabox-development-discipline.md`)
- Create: `cosinabox/.claude/settings.json` (SessionStart hook for worktree check, parallel to Cantina's)
- Create: `cosinabox/src/cosinabox/__init__.py`
- Create: `cosinabox/src/cosinabox/app.py` (stub)
- Create: `cosinabox/src/cosinabox/cli/__init__.py`
- Create: `cosinabox/src/cosinabox/cli/main.py` (stub click group)
- Create: `cosinabox/tests/__init__.py`
- Create: `cosinabox/tests/conftest.py` (empty pytest config)

This task creates the GitHub repo and the new worktree. Until now, all work was in Cantina; from T1.3 onward, work happens inside the cosinabox repo worktree.

- [ ] **Step 1: Create the GitHub repo (manual, ~3 min)**

```bash
gh repo create cosinabox --private --description "Open-source Chief of Staff in a box" --add-readme=false
```

The repo is created **private** for v0.1 development. It flips public in Plan 3. Use Rovik's personal GitHub account (not Cantina org) per spec Section 7.

- [ ] **Step 2: Clone and create the working worktree**

```bash
cd ~
git clone git@github.com:rovikrobert/cosinabox.git
cd cosinabox
git worktree add ~/.worktrees/cosinabox/m1-bootstrap -b chore/m1-bootstrap
cd ~/.worktrees/cosinabox/m1-bootstrap
```

From this point, **every cosinabox file you create lives in `~/.worktrees/cosinabox/m1-bootstrap/`** (or a later worktree).

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "cosinabox"
version = "0.1.0"
description = "Open-source Chief of Staff in a box. Opinionated, proactive, runs on your own infra."
readme = "README.md"
requires-python = ">=3.11"
license = "AGPL-3.0-or-later"
authors = [{ name = "Rovik" }]
dependencies = [
  "anthropic>=0.40",
  "python-telegram-bot>=21.0",
  "apscheduler>=3.10",
  "pyyaml>=6.0",
  "jsonschema>=4.21",
  "click>=8.1",
  "jinja2>=3.1",
  "python-dotenv>=1.0",
]

[project.optional-dependencies]
google = [
  "google-api-python-client>=2.120",
  "google-auth-oauthlib>=1.2",
  "google-auth-httplib2>=0.2",
]
fireflies = ["httpx>=0.27"]
search = ["httpx>=0.27"]
dev = [
  "pytest>=8.0",
  "pytest-asyncio>=0.23",
  "ruff>=0.4",
  "mypy>=1.10",
  "pre-commit>=3.7",
  "types-PyYAML",
  "types-jsonschema",
]

[project.scripts]
cosinabox = "cosinabox.cli.main:cli"

[tool.hatch.build.targets.wheel]
packages = ["src/cosinabox"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]

[tool.mypy]
strict = true
python_version = "3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 4: Write `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
.venv/
dist/
build/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.env
*.db
.DS_Store
```

- [ ] **Step 5: Write `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.10
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies:
          - types-PyYAML
          - types-jsonschema
        args: [src/cosinabox]
        pass_filenames: false
  - repo: local
    hooks:
      - id: pytest-changed
        name: pytest (changed files)
        entry: pytest --picked --mode=branch -q
        language: system
        pass_filenames: false
        stages: [commit]
      - id: secret-scan
        name: secret-scan
        entry: bash -c 'git diff --cached --name-only -z | xargs -0 grep -lE "(sk-ant-|xoxb-|AIza[0-9A-Za-z_-]{35}|ghp_[A-Za-z0-9]{36})" && exit 1 || exit 0'
        language: system
        pass_filenames: false
        stages: [commit]
```

If `pytest --picked` is unfamiliar, use `pytest -q` for now and add `pytest-picked` to dev deps later.

- [ ] **Step 6: Write `.github/workflows/test.yml`**

```yaml
name: test
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev,google]"
      - run: ruff check src tests
      - run: ruff format --check src tests
      - run: mypy src/cosinabox
      - run: pytest -q
```

- [ ] **Step 7: Copy CLAUDE.md from the planning artifact**

```bash
# From the cosinabox worktree:
cp /Users/rovikrobert/Cantina/docs/superpowers/plans/2026-04-11-cosinabox-engine-claude-md.md /tmp/claude-draft.md
# Strip the front-matter (lines 1-9) and write to cosinabox/CLAUDE.md
sed -n '11,$p' /tmp/claude-draft.md > CLAUDE.md
```

Verify the file starts with `# CLAUDE.md — cosinabox engine repository`. If not, adjust the line range.

- [ ] **Step 8: Mirror the discipline doc**

```bash
mkdir -p docs/discipline docs/retros docs/superpowers/specs docs/superpowers/plans
cp /Users/rovikrobert/Cantina/docs/discipline/cosinabox-development-discipline.md docs/discipline/
```

In a follow-up commit (or this same one), update the doc's "Scope" line to reference the cosinabox repo instead of Cantina.

- [ ] **Step 9: Write `.claude/settings.json` (SessionStart hook)**

Mirror the structure of `Cantina/.claude/settings.json` SessionStart hook, but point at `~/.worktrees/cosinabox/...`. Concrete file:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "command": ".claude/hooks/session-start-worktree-check.sh",
        "matchers": []
      }
    ]
  }
}
```

And the script `.claude/hooks/session-start-worktree-check.sh`:

```bash
#!/bin/bash
set -e
PWD_ABS=$(pwd -P)
if [[ "$PWD_ABS" != "$HOME/.worktrees/cosinabox/"* ]]; then
  echo "::warning::Not in a cosinabox worktree. Current path: $PWD_ABS"
  echo "::warning::Run: git worktree add ~/.worktrees/cosinabox/<branch> -b <branch>"
fi
exit 0
```

```bash
chmod +x .claude/hooks/session-start-worktree-check.sh
```

- [ ] **Step 10: Write `src/cosinabox/__init__.py` and stub `app.py` + `cli/main.py`**

`src/cosinabox/__init__.py`:

```python
"""cosinabox — open-source Chief of Staff in a box."""

__version__ = "0.1.0"
```

`src/cosinabox/app.py`:

```python
"""Top-level App entry point. Filled in during M2."""

from __future__ import annotations


class App:
    """Compose personality + stakeholders + jobs and run the bot + scheduler."""

    def __init__(self, config_dir: str | None = None) -> None:
        self.config_dir = config_dir

    def run(self) -> None:
        raise NotImplementedError("App.run lands in Plan 1 Milestone 2")
```

`src/cosinabox/cli/__init__.py`:

```python
"""cosinabox CLI."""
```

`src/cosinabox/cli/main.py`:

```python
"""cosinabox CLI entry point."""

from __future__ import annotations

import click


@click.group()
@click.version_option()
def cli() -> None:
    """CoSinaBox — open-source Chief of Staff."""


if __name__ == "__main__":
    cli()
```

- [ ] **Step 11: Write `tests/conftest.py` and a smoke test**

`tests/conftest.py`:

```python
"""Shared pytest fixtures."""
```

`tests/unit/test_smoke.py`:

```python
def test_package_imports() -> None:
    import cosinabox

    assert cosinabox.__version__ == "0.1.0"


def test_cli_imports() -> None:
    from cosinabox.cli.main import cli

    assert cli.name == "cli"
```

- [ ] **Step 12: Install dev dependencies and run the suite**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,google]"
pre-commit install
ruff check src tests
ruff format --check src tests
mypy src/cosinabox
pytest -q
```

Expected: 2 passed (the smoke tests). Lint + type-check clean.

- [ ] **Step 13: Commit and push**

```bash
git add .
git commit -m "chore: bootstrap cosinabox repo (Plan 1, Task T1.2)"
git push -u origin chore/m1-bootstrap
```

- [ ] **Step 14: Open the M1 PR (will receive subsequent task commits)**

```bash
gh pr create --title "Plan 1 Milestone 1: engine extraction" --body "$(cat <<'EOF'
## Summary
Bootstraps the cosinabox engine repo and ports the generic components from cos-agent (memory, cost tracker, router, agent loop, Telegram bot adapter, Google tools, Fireflies, web search, prompts).

This PR collects all M1 task commits (T1.2 through T1.13). Auto-merges when CI passes.

## Test plan
- [ ] CI green (ruff + mypy + pytest)
- [ ] All ported modules importable
- [ ] Unit tests pass for every ported component
EOF
)"
gh pr merge --auto --squash --delete-branch
```

(Auto-merge requires the cosinabox repo to have `Allow auto-merge` enabled and a branch protection rule on `main`. Per `docs/discipline/cosinabox-development-discipline.md` Manual setup steps, do this immediately after `gh repo create`.)

---

### Task T1.3: Port the SQLite memory layer

**Est:** 2 hr

**Files:**
- Create: `src/cosinabox/memory/__init__.py`
- Create: `src/cosinabox/memory/sqlite.py`
- Create: `tests/unit/test_memory.py`
- Reference (read-only): `cos-agent/src/memory.py`, `cos-agent/config/schema.sql`

The memory layer stores conversation history and the lightweight in-process key-value cache. Schema unchanged from cos-agent. The class is `Memory` and exposes `store_message`, `recent_messages`, `clear_old`, `summary` methods.

- [ ] **Step 1: Read the source**

```bash
cat /Users/rovikrobert/Cantina/cos-agent/src/memory.py
cat /Users/rovikrobert/Cantina/cos-agent/config/schema.sql
```

Note any Rovik-specific column names, hardcoded paths, or magic numbers. The port keeps the schema and the public interface; everything else is fair game to tidy.

- [ ] **Step 2: Write the failing test**

`tests/unit/test_memory.py`:

```python
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cosinabox.memory.sqlite import Memory


@pytest.fixture
def memory(tmp_path: Path) -> Memory:
    return Memory(db_path=tmp_path / "test.db")


def test_store_and_recent(memory: Memory) -> None:
    memory.store_message(role="user", content="hello", session_id="s1")
    memory.store_message(role="assistant", content="hi back", session_id="s1")
    msgs = memory.recent_messages(session_id="s1", limit=10)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["content"] == "hi back"


def test_session_isolation(memory: Memory) -> None:
    memory.store_message(role="user", content="A", session_id="s1")
    memory.store_message(role="user", content="B", session_id="s2")
    assert len(memory.recent_messages(session_id="s1")) == 1
    assert memory.recent_messages(session_id="s1")[0]["content"] == "A"


def test_clear_old(memory: Memory) -> None:
    from datetime import datetime, timedelta, timezone

    old = datetime.now(timezone.utc) - timedelta(days=45)
    memory.store_message(role="user", content="ancient", session_id="s1", timestamp=old)
    memory.store_message(role="user", content="fresh", session_id="s1")
    memory.clear_old(older_than_days=30)
    msgs = memory.recent_messages(session_id="s1")
    assert len(msgs) == 1
    assert msgs[0]["content"] == "fresh"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/unit/test_memory.py -v
```

Expected: ImportError or ModuleNotFoundError on `cosinabox.memory.sqlite`.

- [ ] **Step 4: Implement `src/cosinabox/memory/__init__.py`**

```python
"""SQLite-backed memory layer for cosinabox."""

from cosinabox.memory.sqlite import Memory

__all__ = ["Memory"]
```

- [ ] **Step 5: Implement `src/cosinabox/memory/sqlite.py`**

Port `cos-agent/src/memory.py`. The minimum public surface required by the test:

```python
"""SQLite memory backend.

Schema:
    CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp TEXT NOT NULL  -- ISO-8601 UTC
    );
    CREATE INDEX idx_messages_session_ts ON messages (session_id, timestamp);
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session_ts
    ON messages (session_id, timestamp);
"""


class Memory:
    """SQLite-backed conversation memory.

    Each row is a single message. Session isolation is by `session_id`.
    Scheduled jobs use a fresh session_id per run (see Layer 1 default
    "Scheduled jobs use isolated session contexts").
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def store_message(
        self,
        *,
        role: str,
        content: str,
        session_id: str,
        timestamp: datetime | None = None,
    ) -> None:
        ts = (timestamp or datetime.now(timezone.utc)).isoformat()
        self._conn.execute(
            "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?,?,?,?)",
            (session_id, role, content, ts),
        )
        self._conn.commit()

    def recent_messages(
        self, *, session_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT role, content, timestamp FROM messages "
            "WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]

    def clear_old(self, *, older_than_days: int) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=older_than_days)
        ).isoformat()
        cur = self._conn.execute(
            "DELETE FROM messages WHERE timestamp < ?", (cutoff,)
        )
        self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/unit/test_memory.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Run lint + type checks**

```bash
ruff check src/cosinabox/memory tests/unit/test_memory.py
mypy src/cosinabox/memory
```

Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add src/cosinabox/memory tests/unit/test_memory.py
git commit -m "feat(memory): SQLite memory layer (Plan 1, Task T1.3)"
```

---

### Task T1.4: Port the cost tracker

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/agent/__init__.py`
- Create: `src/cosinabox/agent/cost.py`
- Create: `tests/unit/test_cost.py`
- Reference (read-only): `cos-agent/src/cost_tracker.py`

Cost tracker enforces a per-message cap and a daily cap. Both defaults come from spec Layer 1: per-message $0.75, daily $15. Defaults live in `defaults.py` (T2.1) — until then, the cost tracker accepts caps as constructor arguments.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_cost.py`:

```python
from __future__ import annotations

from datetime import date

import pytest

from cosinabox.agent.cost import CostExceeded, CostTracker


def test_per_message_cap_blocks_oversized_call() -> None:
    tracker = CostTracker(per_message_cap_usd=0.50, daily_cap_usd=10.00)
    with pytest.raises(CostExceeded, match="per-message"):
        tracker.check_message_cost(0.75)


def test_daily_cap_accumulates_across_messages() -> None:
    tracker = CostTracker(per_message_cap_usd=1.00, daily_cap_usd=2.00)
    tracker.record(0.80, on_date=date(2026, 4, 12))
    tracker.record(0.80, on_date=date(2026, 4, 12))
    with pytest.raises(CostExceeded, match="daily"):
        tracker.record(0.80, on_date=date(2026, 4, 12))


def test_daily_cap_resets_next_day() -> None:
    tracker = CostTracker(per_message_cap_usd=1.00, daily_cap_usd=1.00)
    tracker.record(0.99, on_date=date(2026, 4, 11))
    tracker.record(0.99, on_date=date(2026, 4, 12))  # different day, fine
    assert tracker.spend_on(date(2026, 4, 12)) == pytest.approx(0.99)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_cost.py -v
```

Expected: ImportError on `cosinabox.agent.cost`.

- [ ] **Step 3: Implement `src/cosinabox/agent/__init__.py`**

```python
"""Agent loop, routing, cost tracking, summarization."""
```

- [ ] **Step 4: Implement `src/cosinabox/agent/cost.py`**

```python
"""Per-message and daily cost caps for the agent loop.

Defaults come from spec Layer 1:
- Per-message cap: $0.75 (cost runaways are real)
- Daily cap: $15 (forcing function for greedy prompts)

The constants live in defaults.py once that module exists (Task T2.1).
Until then, callers pass caps explicitly.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone


class CostExceeded(Exception):
    """Raised when a cost cap would be exceeded by the next call."""


class CostTracker:
    def __init__(
        self,
        *,
        per_message_cap_usd: float,
        daily_cap_usd: float,
    ) -> None:
        self.per_message_cap_usd = per_message_cap_usd
        self.daily_cap_usd = daily_cap_usd
        self._daily_spend: dict[date, float] = defaultdict(float)

    def check_message_cost(self, estimated_usd: float) -> None:
        if estimated_usd > self.per_message_cap_usd:
            raise CostExceeded(
                f"per-message cost ${estimated_usd:.4f} exceeds cap "
                f"${self.per_message_cap_usd:.4f}"
            )

    def record(self, actual_usd: float, *, on_date: date | None = None) -> None:
        d = on_date or datetime.now(timezone.utc).date()
        if self._daily_spend[d] + actual_usd > self.daily_cap_usd:
            raise CostExceeded(
                f"daily spend ${self._daily_spend[d] + actual_usd:.4f} "
                f"exceeds cap ${self.daily_cap_usd:.4f}"
            )
        self._daily_spend[d] += actual_usd

    def spend_on(self, d: date) -> float:
        return self._daily_spend[d]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/unit/test_cost.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Lint + type-check + commit**

```bash
ruff check src/cosinabox/agent tests/unit/test_cost.py
mypy src/cosinabox/agent
git add src/cosinabox/agent tests/unit/test_cost.py
git commit -m "feat(agent): cost tracker with per-message and daily caps (Plan 1, Task T1.4)"
```

---

### Task T1.5: Port the router

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/agent/routing.py`
- Create: `tests/unit/test_routing.py`
- Reference (read-only): `cos-agent/src/router.py`, `cos-agent/config/tool_subsets.py`

The router decides (a) which Claude model to use (Sonnet by default, Opus on strategic-keyword prompts per Layer 1) and (b) which tool subset is available in the current channel mode (DM vs group). Cos-agent's router has Rovik-specific keyword lists; the cosinabox version starts with a small generic strategic-keyword list and lets users override via personality.md or jobs.yaml in the future.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_routing.py`:

```python
from __future__ import annotations

from cosinabox.agent.routing import Router


def test_default_model_is_sonnet() -> None:
    router = Router()
    assert router.choose_model("what time is my next meeting?") == "claude-sonnet-4-6"


def test_strategic_keyword_routes_to_opus() -> None:
    router = Router()
    assert router.choose_model("Help me think through our hiring strategy") == "claude-opus-4-6"
    assert router.choose_model("Draft a board update") == "claude-opus-4-6"


def test_dm_mode_allows_full_tool_set() -> None:
    router = Router(available_tools={"gmail", "calendar", "web_search"})
    assert router.tools_for_channel("dm") == {"gmail", "calendar", "web_search"}


def test_group_mode_restricted_to_safe_subset() -> None:
    router = Router(available_tools={"gmail", "calendar", "web_search"})
    assert router.tools_for_channel("group") == {"calendar", "web_search"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_routing.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `src/cosinabox/agent/routing.py`**

```python
"""Model routing and per-channel tool subsets.

Layer 1 defaults:
- Sonnet by default; Opus on strategic-keyword prompts
- Group chats restricted to calendar + web_search (group mode exposes
  too much surface)
"""

from __future__ import annotations

DEFAULT_STRATEGIC_KEYWORDS = frozenset(
    {
        "strategy",
        "strategic",
        "hiring",
        "fundraise",
        "fundraising",
        "board",
        "investors",
        "vision",
        "roadmap",
        "OKR",
        "OKRs",
    }
)

GROUP_SAFE_TOOLS = frozenset({"calendar", "web_search"})

SONNET_MODEL_ID = "claude-sonnet-4-6"
OPUS_MODEL_ID = "claude-opus-4-6"


class Router:
    def __init__(
        self,
        *,
        available_tools: set[str] | None = None,
        strategic_keywords: frozenset[str] = DEFAULT_STRATEGIC_KEYWORDS,
    ) -> None:
        self.available_tools = available_tools or set()
        self.strategic_keywords = strategic_keywords

    def choose_model(self, prompt: str) -> str:
        lowered = prompt.lower()
        if any(kw.lower() in lowered for kw in self.strategic_keywords):
            return OPUS_MODEL_ID
        return SONNET_MODEL_ID

    def tools_for_channel(self, channel: str) -> set[str]:
        if channel == "group":
            return self.available_tools & GROUP_SAFE_TOOLS
        return set(self.available_tools)
```

- [ ] **Step 4: Run tests to verify they pass + commit**

```bash
pytest tests/unit/test_routing.py -v
ruff check src/cosinabox/agent tests/unit/test_routing.py
mypy src/cosinabox/agent
git add src/cosinabox/agent/routing.py tests/unit/test_routing.py
git commit -m "feat(agent): router with model + tool-subset selection (Plan 1, Task T1.5)"
```

---

### Task T1.6: Port the agent loop

**Est:** 4 hr

**Files:**
- Create: `src/cosinabox/agent/loop.py`
- Create: `tests/unit/test_agent_loop.py`
- Create: `tests/integration/test_agent_loop.py`
- Reference (read-only): `cos-agent/src/agent.py`

The agent loop is the heart of cosinabox: a single iteration calls Anthropic, parses tool calls, dispatches them, feeds results back, and stops when (a) the model returns a final text-only response, (b) `MAX_TOOL_ITERATIONS` is hit, or (c) the cost cap raises. Strip every Rovik-specific routing rule from cos-agent's version.

- [ ] **Step 1: Read the source**

```bash
cat /Users/rovikrobert/Cantina/cos-agent/src/agent.py | head -200
```

Look for: hardcoded model IDs (push to Router), hardcoded "Daniel" / "Cantina" / "Rovik" strings (DROP), per-tool special-casing (push to per-tool modules), session ID handling (keep), prompt-injection wrapping of tool results (KEEP — Layer 1).

- [ ] **Step 2: Write the failing unit test (mocks Anthropic)**

`tests/unit/test_agent_loop.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

from cosinabox.agent.cost import CostTracker
from cosinabox.agent.loop import AgentLoop, ToolCall
from cosinabox.agent.routing import Router


def make_loop(anthropic_responses: list, tools: dict | None = None) -> AgentLoop:
    client = MagicMock()
    client.messages.create.side_effect = anthropic_responses
    return AgentLoop(
        anthropic_client=client,
        router=Router(available_tools=set(tools.keys()) if tools else set()),
        cost_tracker=CostTracker(per_message_cap_usd=10, daily_cap_usd=100),
        tools=tools or {},
        max_tool_iterations=8,
    )


def _text_response(text: str):
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [MagicMock(type="text", text=text)]
    resp.usage.input_tokens = 100
    resp.usage.output_tokens = 50
    return resp


def _tool_call_response(name: str, tool_use_id: str, args: dict):
    resp = MagicMock()
    resp.stop_reason = "tool_use"
    block = MagicMock(type="tool_use", id=tool_use_id, name=name, input=args)
    resp.content = [block]
    resp.usage.input_tokens = 100
    resp.usage.output_tokens = 50
    return resp


def test_text_only_response_returns_immediately() -> None:
    loop = make_loop([_text_response("Hello!")])
    result = loop.run(prompt="hi", session_id="s1")
    assert result.final_text == "Hello!"
    assert result.tool_calls == []


def test_single_tool_call_then_final_text() -> None:
    fake_tool = MagicMock(return_value="It is sunny.")
    loop = make_loop(
        [
            _tool_call_response("weather", "tu_1", {"city": "SF"}),
            _text_response("The weather in SF is sunny."),
        ],
        tools={"weather": fake_tool},
    )
    result = loop.run(prompt="weather in SF?", session_id="s1")
    fake_tool.assert_called_once_with(city="SF")
    assert result.final_text == "The weather in SF is sunny."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "weather"


def test_max_iterations_breaks_loop() -> None:
    loop = make_loop(
        [_tool_call_response("noop", f"tu_{i}", {}) for i in range(10)],
        tools={"noop": MagicMock(return_value="ok")},
    )
    loop.max_tool_iterations = 3
    result = loop.run(prompt="loop forever", session_id="s1")
    assert result.stopped_reason == "max_iterations"
    assert len(result.tool_calls) == 3
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/unit/test_agent_loop.py -v
```

Expected: ImportError.

- [ ] **Step 4: Implement `src/cosinabox/agent/loop.py`**

```python
"""Agent loop: Anthropic call, tool dispatch, iteration, stop conditions."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from cosinabox.agent.cost import CostExceeded, CostTracker
from cosinabox.agent.routing import Router


class AnthropicClient(Protocol):
    messages: Any  # duck-typed against the real anthropic.Anthropic client


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    result: str
    tool_use_id: str


@dataclass
class LoopResult:
    final_text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stopped_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0


def _wrap_untrusted(data: str) -> str:
    """Wrap external tool output to defend against prompt injection.

    Layer 1: tool results need prompt-injection defense.
    """
    return (
        "<untrusted_tool_output>\n"
        + data
        + "\n</untrusted_tool_output>"
    )


class AgentLoop:
    def __init__(
        self,
        *,
        anthropic_client: AnthropicClient,
        router: Router,
        cost_tracker: CostTracker,
        tools: dict[str, Callable[..., str]],
        max_tool_iterations: int = 8,
        tool_iteration_delay_s: float = 2.0,
    ) -> None:
        self.client = anthropic_client
        self.router = router
        self.cost = cost_tracker
        self.tools = tools
        self.max_tool_iterations = max_tool_iterations
        self.tool_iteration_delay_s = tool_iteration_delay_s

    def run(self, *, prompt: str, session_id: str) -> LoopResult:
        model = self.router.choose_model(prompt)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        result = LoopResult(final_text="")
        for iteration in range(self.max_tool_iterations):
            try:
                response = self.client.messages.create(
                    model=model,
                    max_tokens=4096,
                    messages=messages,
                )
            except CostExceeded:
                result.stopped_reason = "cost_exceeded"
                return result
            result.input_tokens += response.usage.input_tokens
            result.output_tokens += response.usage.output_tokens
            if response.stop_reason == "end_turn":
                text_blocks = [b.text for b in response.content if b.type == "text"]
                result.final_text = "\n".join(text_blocks)
                return result
            if response.stop_reason == "tool_use":
                tool_blocks = [b for b in response.content if b.type == "tool_use"]
                tool_results: list[dict[str, Any]] = []
                for block in tool_blocks:
                    fn = self.tools.get(block.name)
                    if fn is None:
                        raw = f"Tool '{block.name}' not configured"
                    else:
                        raw = str(fn(**block.input))
                    wrapped = _wrap_untrusted(raw)
                    result.tool_calls.append(
                        ToolCall(
                            name=block.name,
                            args=dict(block.input),
                            result=raw,
                            tool_use_id=block.id,
                        )
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": wrapped,
                        }
                    )
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
                if iteration < self.max_tool_iterations - 1:
                    time.sleep(self.tool_iteration_delay_s)
                continue
            result.stopped_reason = response.stop_reason or "unknown"
            return result
        result.stopped_reason = "max_iterations"
        return result
```

- [ ] **Step 5: Run unit tests to verify they pass**

```bash
pytest tests/unit/test_agent_loop.py -v
```

Expected: 3 passed. The mocked `time.sleep` will slow tests; if it does, monkeypatch `time.sleep` in the test fixture to a no-op.

- [ ] **Step 6: Write the integration test (against a recorded fixture, NOT the live API)**

`tests/integration/__init__.py`:

```python
```

`tests/integration/test_agent_loop.py`:

```python
"""Integration test: AgentLoop against a deterministic recorded transcript."""

from __future__ import annotations

from cosinabox.agent.cost import CostTracker
from cosinabox.agent.loop import AgentLoop
from cosinabox.agent.routing import Router


class _StubResponseClient:
    """Returns canned Anthropic responses in order."""

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.messages = self  # duck-type

    def create(self, **kwargs):  # noqa: ARG002
        return self._responses.pop(0)


def test_loop_aborts_when_cost_tracker_blocks(monkeypatch) -> None:
    monkeypatch.setattr("cosinabox.agent.loop.time.sleep", lambda *_: None)
    cost = CostTracker(per_message_cap_usd=0.01, daily_cap_usd=0.01)
    cost.record(0.01)  # exhaust daily cap

    class _BoomClient:
        messages = None

        @staticmethod
        def create(**_):
            from cosinabox.agent.cost import CostExceeded

            raise CostExceeded("daily")

    loop = AgentLoop(
        anthropic_client=_BoomClient(),
        router=Router(),
        cost_tracker=cost,
        tools={},
    )
    result = loop.run(prompt="hi", session_id="s1")
    assert result.stopped_reason == "cost_exceeded"
```

- [ ] **Step 7: Run integration tests + commit**

```bash
pytest tests/unit/test_agent_loop.py tests/integration/test_agent_loop.py -v
ruff check src/cosinabox/agent tests/unit/test_agent_loop.py tests/integration/test_agent_loop.py
mypy src/cosinabox/agent
git add src/cosinabox/agent/loop.py tests/unit/test_agent_loop.py tests/integration/test_agent_loop.py
git commit -m "feat(agent): agent loop with tool dispatch + injection defense (Plan 1, Task T1.6)"
```

---

### Task T1.7: Port the Telegram bot adapter

**Est:** 3 hr

**Files:**
- Create: `src/cosinabox/bot/__init__.py`
- Create: `src/cosinabox/bot/telegram.py`
- Create: `tests/unit/test_bot_telegram.py`
- Reference (read-only): `cos-agent/src/bot.py`, `cos-agent/src/bot_commands.py`

Cos-agent's bot supports two Telegram accounts (Rovik's personal + Cantina shared). The cosinabox version is single-account. It exposes `TelegramBot` with `send(chat_id, text)`, `start_polling()`, and `register_message_handler(callback)`. DM vs group mode is decided by `update.effective_chat.type`. Voice/photo/PDF handling: keep the cos-agent shape but generalize.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_bot_telegram.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cosinabox.bot.telegram import TelegramBot


@pytest.fixture
def bot() -> TelegramBot:
    return TelegramBot(token="fake-token")


async def test_send_calls_telegram_api(bot: TelegramBot, monkeypatch) -> None:
    fake_app = MagicMock()
    fake_app.bot.send_message = AsyncMock()
    monkeypatch.setattr(bot, "_app", fake_app)
    await bot.send(chat_id=12345, text="hello")
    fake_app.bot.send_message.assert_awaited_once_with(chat_id=12345, text="hello")


async def test_classify_chat_dm_vs_group(bot: TelegramBot) -> None:
    dm_update = MagicMock()
    dm_update.effective_chat.type = "private"
    group_update = MagicMock()
    group_update.effective_chat.type = "supergroup"
    assert bot.classify(dm_update) == "dm"
    assert bot.classify(group_update) == "group"


async def test_register_handler_records_callback(bot: TelegramBot) -> None:
    cb = AsyncMock()
    bot.register_message_handler(cb)
    assert cb in bot._handlers
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_bot_telegram.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `src/cosinabox/bot/__init__.py`**

```python
"""Telegram adapter (only outbound channel in v0.1)."""

from cosinabox.bot.telegram import TelegramBot

__all__ = ["TelegramBot"]
```

- [ ] **Step 4: Implement `src/cosinabox/bot/telegram.py`**

```python
"""Telegram bot adapter — single-account, DM + group modes."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from telegram import Update
from telegram.ext import Application, MessageHandler, filters

ChatMode = str  # "dm" | "group"
MessageHandlerFn = Callable[[Update, ChatMode], Awaitable[None]]


class TelegramBot:
    def __init__(self, token: str) -> None:
        self.token = token
        self._handlers: list[MessageHandlerFn] = []
        self._app: Application | None = None

    def register_message_handler(self, handler: MessageHandlerFn) -> None:
        self._handlers.append(handler)

    @staticmethod
    def classify(update: Update) -> ChatMode:
        if update.effective_chat is None:
            return "dm"
        return "dm" if update.effective_chat.type == "private" else "group"

    async def send(self, *, chat_id: int, text: str) -> None:
        assert self._app is not None, "bot not started; call start_polling first"
        await self._app.bot.send_message(chat_id=chat_id, text=text)

    async def _on_message(self, update: Update, _ctx: Any) -> None:
        mode = self.classify(update)
        for handler in self._handlers:
            await handler(update, mode)

    def start_polling(self) -> None:
        self._app = Application.builder().token(self.token).build()
        self._app.add_handler(MessageHandler(filters.ALL, self._on_message))
        self._app.run_polling()
```

The voice/photo/PDF handling from cos-agent is **not** in this MVP — file-handling tools will land in v0.2. Surface this in the milestone retro: if voice/photo are needed for parity with cos-agent, schedule them in Plan 2.

- [ ] **Step 5: Run tests + lint + commit**

```bash
pytest tests/unit/test_bot_telegram.py -v
ruff check src/cosinabox/bot tests/unit/test_bot_telegram.py
mypy src/cosinabox/bot
git add src/cosinabox/bot tests/unit/test_bot_telegram.py
git commit -m "feat(bot): single-account Telegram adapter (Plan 1, Task T1.7)"
```

---

### Task T1.8: Port Google OAuth helper

**Est:** 2 hr

**Files:**
- Create: `src/cosinabox/tools/__init__.py`
- Create: `src/cosinabox/tools/google/__init__.py`
- Create: `src/cosinabox/tools/google/auth.py`
- Create: `tests/unit/test_google_auth.py`
- Reference (read-only): `cos-agent/src/tools/google_auth.py`, `cos-agent/src/tools/auth_context.py`

Single-account default. Loads `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, and `GOOGLE_OAUTH_REFRESH_TOKEN` from environment, builds a `google.oauth2.credentials.Credentials` object, and refreshes when stale.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_google_auth.py`:

```python
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from cosinabox.tools.google.auth import (
    GoogleAuthError,
    build_credentials,
)


def test_missing_env_raises() -> None:
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(GoogleAuthError, match="GOOGLE_OAUTH_CLIENT_ID"):
            build_credentials()


def test_env_present_returns_credentials() -> None:
    env = {
        "GOOGLE_OAUTH_CLIENT_ID": "cid",
        "GOOGLE_OAUTH_CLIENT_SECRET": "secret",
        "GOOGLE_OAUTH_REFRESH_TOKEN": "rtoken",
    }
    with patch.dict(os.environ, env, clear=True):
        with patch("cosinabox.tools.google.auth.Credentials") as MockCreds:
            instance = MagicMock()
            MockCreds.return_value = instance
            creds = build_credentials()
            assert creds is instance
            MockCreds.assert_called_once()
            kwargs = MockCreds.call_args.kwargs
            assert kwargs["client_id"] == "cid"
            assert kwargs["client_secret"] == "secret"
            assert kwargs["refresh_token"] == "rtoken"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_google_auth.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement files**

`src/cosinabox/tools/__init__.py`:

```python
"""Built-in tool catalog."""
```

`src/cosinabox/tools/google/__init__.py`:

```python
"""Google integration: OAuth, Gmail, Calendar."""
```

`src/cosinabox/tools/google/auth.py`:

```python
"""Google OAuth helper — single-account default.

Loads refresh token from env. Use `cosinabox auth google` (Task T4.11)
to mint a refresh token interactively.
"""

from __future__ import annotations

import os

try:
    from google.oauth2.credentials import Credentials
except ImportError as e:  # optional dep
    raise ImportError(
        "cosinabox[google] extra is required. Run: pip install 'cosinabox[google]'"
    ) from e

GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_DEFAULT_SCOPES = (
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
)


class GoogleAuthError(Exception):
    pass


def build_credentials() -> Credentials:
    cid = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    refresh = os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN")
    missing = [
        n
        for n, v in (
            ("GOOGLE_OAUTH_CLIENT_ID", cid),
            ("GOOGLE_OAUTH_CLIENT_SECRET", secret),
            ("GOOGLE_OAUTH_REFRESH_TOKEN", refresh),
        )
        if not v
    ]
    if missing:
        raise GoogleAuthError(
            f"Missing required env vars: {', '.join(missing)}. "
            "Run `cosinabox auth google` to mint a refresh token."
        )
    return Credentials(
        token=None,
        refresh_token=refresh,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=cid,
        client_secret=secret,
        scopes=list(GOOGLE_DEFAULT_SCOPES),
    )
```

- [ ] **Step 4: Run tests + commit**

```bash
pytest tests/unit/test_google_auth.py -v
ruff check src/cosinabox/tools/google tests/unit/test_google_auth.py
mypy src/cosinabox/tools/google
git add src/cosinabox/tools tests/unit/test_google_auth.py
git commit -m "feat(tools/google): single-account OAuth helper (Plan 1, Task T1.8)"
```

---

### Task T1.9: Port Gmail tool

**Est:** 2 hr

**Files:**
- Create: `src/cosinabox/tools/google/gmail.py`
- Create: `tests/unit/test_google_gmail.py`
- Reference (read-only): `cos-agent/src/tools/gmail_tool.py`, `cos-agent/src/tools/gmail_helpers.py`

Public surface (the loop calls these as tools):
- `list_recent(*, hours: int = 24, max_results: int = 25) -> list[GmailMessage]`
- `get_thread(thread_id: str) -> GmailThread`
- `search(query: str, max_results: int = 25) -> list[GmailMessage]`

Mock the underlying service in tests; never call real Gmail.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_google_gmail.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

from cosinabox.tools.google.gmail import GmailTool


def _fake_service_with_messages(messages: list[dict]) -> MagicMock:
    svc = MagicMock()
    list_call = MagicMock()
    list_call.execute.return_value = {"messages": [{"id": m["id"]} for m in messages]}
    svc.users.return_value.messages.return_value.list.return_value = list_call
    by_id = {m["id"]: m for m in messages}

    def get_side_effect(userId, id, format):  # noqa: ARG001
        get_call = MagicMock()
        get_call.execute.return_value = by_id[id]
        return get_call

    svc.users.return_value.messages.return_value.get.side_effect = get_side_effect
    return svc


def test_list_recent_returns_parsed_messages() -> None:
    svc = _fake_service_with_messages(
        [
            {
                "id": "m1",
                "snippet": "hello",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Alice <a@x.com>"},
                        {"name": "Subject", "value": "Hi"},
                        {"name": "Date", "value": "Mon, 12 Apr 2026 09:00:00 +0000"},
                    ]
                },
            }
        ]
    )
    tool = GmailTool(service=svc)
    msgs = tool.list_recent(hours=24)
    assert len(msgs) == 1
    assert msgs[0].sender == "Alice <a@x.com>"
    assert msgs[0].subject == "Hi"
    assert msgs[0].snippet == "hello"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_google_gmail.py -v
```

- [ ] **Step 3: Implement `src/cosinabox/tools/google/gmail.py`**

```python
"""Gmail tool — read-only listing and search."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from googleapiclient.discovery import Resource, build
except ImportError as e:
    raise ImportError(
        "cosinabox[google] extra is required. Run: pip install 'cosinabox[google]'"
    ) from e

from cosinabox.tools.google.auth import build_credentials


@dataclass
class GmailMessage:
    id: str
    sender: str
    subject: str
    snippet: str
    date: str


def _header(payload: dict[str, Any], name: str) -> str:
    for h in payload.get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


class GmailTool:
    def __init__(self, *, service: Resource | None = None) -> None:
        if service is None:
            service = build("gmail", "v1", credentials=build_credentials())
        self.service = service

    def list_recent(
        self, *, hours: int = 24, max_results: int = 25
    ) -> list[GmailMessage]:
        after = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y/%m/%d")
        query = f"after:{after}"
        resp = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        out: list[GmailMessage] = []
        for ref in resp.get("messages", []):
            full = (
                self.service.users()
                .messages()
                .get(userId="me", id=ref["id"], format="metadata")
                .execute()
            )
            payload = full.get("payload", {})
            out.append(
                GmailMessage(
                    id=full["id"],
                    sender=_header(payload, "From"),
                    subject=_header(payload, "Subject"),
                    snippet=full.get("snippet", ""),
                    date=_header(payload, "Date"),
                )
            )
        return out

    def search(self, query: str, *, max_results: int = 25) -> list[GmailMessage]:
        resp = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        out: list[GmailMessage] = []
        for ref in resp.get("messages", []):
            full = (
                self.service.users()
                .messages()
                .get(userId="me", id=ref["id"], format="metadata")
                .execute()
            )
            payload = full.get("payload", {})
            out.append(
                GmailMessage(
                    id=full["id"],
                    sender=_header(payload, "From"),
                    subject=_header(payload, "Subject"),
                    snippet=full.get("snippet", ""),
                    date=_header(payload, "Date"),
                )
            )
        return out
```

- [ ] **Step 4: Run tests + commit**

```bash
pytest tests/unit/test_google_gmail.py -v
ruff check src/cosinabox/tools/google tests/unit/test_google_gmail.py
mypy src/cosinabox/tools/google
git add src/cosinabox/tools/google/gmail.py tests/unit/test_google_gmail.py
git commit -m "feat(tools/google): Gmail list+search tool (Plan 1, Task T1.9)"
```

---

### Task T1.10: Port Calendar tool with conflict detection

**Est:** 3 hr

**Files:**
- Create: `src/cosinabox/tools/google/calendar.py`
- Create: `tests/unit/test_google_calendar.py`
- Reference (read-only): `cos-agent/src/tools/calendar_tool.py`, `cos-agent/src/tools/calendar_write.py`

Public surface:
- `list_events(*, start: datetime, end: datetime) -> list[CalendarEvent]`
- `create_event(*, summary, start, end, attendees=None) -> CalendarEvent`
- `find_conflicts(*, start, end) -> list[CalendarEvent]`

Conflict detection runs **before every event creation** (Layer 1: calendar double-booking is silent and painful). If conflicts exist, raise `CalendarConflict` and require an explicit override flag.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_google_calendar.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from cosinabox.tools.google.calendar import CalendarConflict, CalendarTool


def _fake_service(events: list[dict]) -> MagicMock:
    svc = MagicMock()
    list_call = MagicMock()
    list_call.execute.return_value = {"items": events}
    svc.events.return_value.list.return_value = list_call
    insert_call = MagicMock()
    insert_call.execute.return_value = {
        "id": "new-evt",
        "summary": "X",
        "start": {"dateTime": "2026-04-12T10:00:00+00:00"},
        "end": {"dateTime": "2026-04-12T11:00:00+00:00"},
    }
    svc.events.return_value.insert.return_value = insert_call
    return svc


def test_find_conflicts_returns_overlapping_events() -> None:
    existing = [
        {
            "id": "e1",
            "summary": "Standup",
            "start": {"dateTime": "2026-04-12T10:00:00+00:00"},
            "end": {"dateTime": "2026-04-12T10:30:00+00:00"},
        }
    ]
    tool = CalendarTool(service=_fake_service(existing))
    start = datetime(2026, 4, 12, 10, 15, tzinfo=timezone.utc)
    end = start + timedelta(minutes=30)
    conflicts = tool.find_conflicts(start=start, end=end)
    assert len(conflicts) == 1
    assert conflicts[0].id == "e1"


def test_create_event_blocks_when_conflict_present() -> None:
    existing = [
        {
            "id": "e1",
            "summary": "Standup",
            "start": {"dateTime": "2026-04-12T10:00:00+00:00"},
            "end": {"dateTime": "2026-04-12T10:30:00+00:00"},
        }
    ]
    tool = CalendarTool(service=_fake_service(existing))
    with pytest.raises(CalendarConflict):
        tool.create_event(
            summary="Coffee",
            start=datetime(2026, 4, 12, 10, 15, tzinfo=timezone.utc),
            end=datetime(2026, 4, 12, 10, 45, tzinfo=timezone.utc),
        )


def test_create_event_with_override_succeeds() -> None:
    existing = [
        {
            "id": "e1",
            "summary": "Standup",
            "start": {"dateTime": "2026-04-12T10:00:00+00:00"},
            "end": {"dateTime": "2026-04-12T10:30:00+00:00"},
        }
    ]
    tool = CalendarTool(service=_fake_service(existing))
    evt = tool.create_event(
        summary="Coffee",
        start=datetime(2026, 4, 12, 10, 15, tzinfo=timezone.utc),
        end=datetime(2026, 4, 12, 10, 45, tzinfo=timezone.utc),
        allow_conflict=True,
    )
    assert evt.id == "new-evt"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_google_calendar.py -v
```

- [ ] **Step 3: Implement `src/cosinabox/tools/google/calendar.py`**

```python
"""Google Calendar tool with conflict detection.

Layer 1: calendar double-booking is silent and painful — every create
runs `find_conflicts` first.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

try:
    from googleapiclient.discovery import Resource, build
except ImportError as e:
    raise ImportError(
        "cosinabox[google] extra is required. Run: pip install 'cosinabox[google]'"
    ) from e

from cosinabox.tools.google.auth import build_credentials


class CalendarConflict(Exception):
    """Raised when create_event would overlap an existing event."""

    def __init__(self, conflicts: list["CalendarEvent"]) -> None:
        self.conflicts = conflicts
        msg = ", ".join(f"{c.summary} ({c.start.isoformat()})" for c in conflicts)
        super().__init__(f"Conflicts: {msg}")


@dataclass
class CalendarEvent:
    id: str
    summary: str
    start: datetime
    end: datetime


def _parse_dt(value: dict[str, Any]) -> datetime:
    raw = value.get("dateTime") or value.get("date")
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


class CalendarTool:
    def __init__(self, *, service: Resource | None = None, calendar_id: str = "primary") -> None:
        if service is None:
            service = build("calendar", "v3", credentials=build_credentials())
        self.service = service
        self.calendar_id = calendar_id

    def list_events(self, *, start: datetime, end: datetime) -> list[CalendarEvent]:
        resp = (
            self.service.events()
            .list(
                calendarId=self.calendar_id,
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return [
            CalendarEvent(
                id=item["id"],
                summary=item.get("summary", ""),
                start=_parse_dt(item["start"]),
                end=_parse_dt(item["end"]),
            )
            for item in resp.get("items", [])
        ]

    def find_conflicts(
        self, *, start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        existing = self.list_events(start=start, end=end)
        return [e for e in existing if e.start < end and e.end > start]

    def create_event(
        self,
        *,
        summary: str,
        start: datetime,
        end: datetime,
        attendees: list[str] | None = None,
        allow_conflict: bool = False,
    ) -> CalendarEvent:
        if not allow_conflict:
            conflicts = self.find_conflicts(start=start, end=end)
            if conflicts:
                raise CalendarConflict(conflicts)
        body = {
            "summary": summary,
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
        }
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        resp = (
            self.service.events()
            .insert(calendarId=self.calendar_id, body=body)
            .execute()
        )
        return CalendarEvent(
            id=resp["id"],
            summary=resp.get("summary", ""),
            start=_parse_dt(resp["start"]),
            end=_parse_dt(resp["end"]),
        )
```

- [ ] **Step 4: Run tests + commit**

```bash
pytest tests/unit/test_google_calendar.py -v
ruff check src/cosinabox/tools/google tests/unit/test_google_calendar.py
mypy src/cosinabox/tools/google
git add src/cosinabox/tools/google/calendar.py tests/unit/test_google_calendar.py
git commit -m "feat(tools/google): Calendar tool with conflict detection (Plan 1, Task T1.10)"
```

---

### Task T1.11: Port Fireflies tool (optional dep)

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/tools/fireflies.py`
- Create: `tests/unit/test_fireflies.py`
- Reference (read-only): `cos-agent/src/tools/fireflies_tool.py`

Optional integration. Uses GraphQL via httpx (the `[fireflies]` extra). Public surface: `list_recent_meetings(hours=24)` and `get_transcript(meeting_id)`. Tests mock httpx.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_fireflies.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

from cosinabox.tools.fireflies import FirefliesTool


def test_list_recent_parses_graphql_response() -> None:
    with patch("cosinabox.tools.fireflies.httpx.Client") as MockClient:
        client = MagicMock()
        MockClient.return_value.__enter__.return_value = client
        client.post.return_value.json.return_value = {
            "data": {
                "transcripts": [
                    {"id": "t1", "title": "Standup", "date": "2026-04-12T10:00:00Z"}
                ]
            }
        }
        tool = FirefliesTool(api_key="fake")
        meetings = tool.list_recent_meetings(hours=24)
        assert len(meetings) == 1
        assert meetings[0]["id"] == "t1"
```

- [ ] **Step 2: Run test to verify it fails + implement**

```bash
pytest tests/unit/test_fireflies.py -v
```

`src/cosinabox/tools/fireflies.py`:

```python
"""Fireflies meeting transcripts (optional dep: cosinabox[fireflies])."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

try:
    import httpx
except ImportError as e:
    raise ImportError(
        "cosinabox[fireflies] extra is required. "
        "Run: pip install 'cosinabox[fireflies]'"
    ) from e

FIREFLIES_GRAPHQL_URL = "https://api.fireflies.ai/graphql"


class FirefliesTool:
    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    def list_recent_meetings(self, *, hours: int = 24) -> list[dict[str, Any]]:
        after = datetime.now(timezone.utc) - timedelta(hours=hours)
        query = """
        query Recent($after: DateTime!) {
            transcripts(fromDate: $after) { id title date }
        }
        """
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                FIREFLIES_GRAPHQL_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"query": query, "variables": {"after": after.isoformat()}},
            )
        return resp.json().get("data", {}).get("transcripts", []) or []

    def get_transcript(self, meeting_id: str) -> dict[str, Any]:
        query = """
        query Transcript($id: String!) {
            transcript(id: $id) { id title sentences { text speaker_name } }
        }
        """
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                FIREFLIES_GRAPHQL_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"query": query, "variables": {"id": meeting_id}},
            )
        return resp.json().get("data", {}).get("transcript", {}) or {}
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_fireflies.py -v
ruff check src/cosinabox/tools/fireflies.py tests/unit/test_fireflies.py
mypy src/cosinabox/tools
git add src/cosinabox/tools/fireflies.py tests/unit/test_fireflies.py
git commit -m "feat(tools): fireflies optional integration (Plan 1, Task T1.11)"
```

---

### Task T1.12: Port web search tool (optional dep)

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/tools/web_search.py`
- Create: `tests/unit/test_web_search.py`
- Reference (read-only): `cos-agent/src/tools/web_search_tool.py`

Uses Serper.dev. Optional via `cosinabox[search]`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_web_search.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

from cosinabox.tools.web_search import WebSearchTool


def test_search_returns_results() -> None:
    with patch("cosinabox.tools.web_search.httpx.Client") as MockClient:
        client = MagicMock()
        MockClient.return_value.__enter__.return_value = client
        client.post.return_value.json.return_value = {
            "organic": [
                {"title": "T1", "link": "https://x.com", "snippet": "S1"},
                {"title": "T2", "link": "https://y.com", "snippet": "S2"},
            ]
        }
        tool = WebSearchTool(api_key="fake")
        results = tool.search("test query")
        assert len(results) == 2
        assert results[0]["title"] == "T1"
```

- [ ] **Step 2: Implement + run + commit**

`src/cosinabox/tools/web_search.py`:

```python
"""Serper.dev web search tool (optional dep: cosinabox[search])."""

from __future__ import annotations

from typing import Any

try:
    import httpx
except ImportError as e:
    raise ImportError(
        "cosinabox[search] extra is required. Run: pip install 'cosinabox[search]'"
    ) from e

SERPER_URL = "https://google.serper.dev/search"


class WebSearchTool:
    def __init__(self, *, api_key: str) -> None:
        self.api_key = api_key

    def search(self, query: str, *, num: int = 10) -> list[dict[str, Any]]:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                SERPER_URL,
                headers={
                    "X-API-KEY": self.api_key,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": num},
            )
        return resp.json().get("organic", []) or []
```

```bash
pytest tests/unit/test_web_search.py -v
ruff check src/cosinabox/tools/web_search.py tests/unit/test_web_search.py
mypy src/cosinabox/tools
git add src/cosinabox/tools/web_search.py tests/unit/test_web_search.py
git commit -m "feat(tools): web search optional integration (Plan 1, Task T1.12)"
```

---

### Task T1.13: Port prompts + summarization

**Est:** 2 hr

**Files:**
- Create: `src/cosinabox/prompts/__init__.py`
- Create: `src/cosinabox/prompts/core.py`
- Create: `src/cosinabox/prompts/briefing.py`
- Create: `src/cosinabox/agent/summarization.py`
- Create: `tests/unit/test_prompts.py`
- Create: `tests/unit/test_summarization.py`
- Reference (read-only): `cos-agent/src/prompts/core.py`, `cos-agent/src/prompts/briefing.py`, `cos-agent/src/agent_summarization.py`

Replace every hardcoded name (`"Daniel"`, `"Cantina"`, `"Rovik"`) with a `{{personality}}` slot. Prompts are Jinja2 templates loaded from string constants. Summarization triggers when message count exceeds threshold (default 25 from spec Layer 1).

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_prompts.py`:

```python
from __future__ import annotations

from cosinabox.prompts.core import render_system_prompt
from cosinabox.prompts.briefing import render_briefing_prompt


def test_system_prompt_substitutes_personality() -> None:
    out = render_system_prompt(
        personality="You are blunt. Cut filler.",
        name="Alex",
        timezone="America/Los_Angeles",
    )
    assert "Alex" in out
    assert "America/Los_Angeles" in out
    assert "blunt" in out


def test_briefing_prompt_includes_sections() -> None:
    out = render_briefing_prompt(
        personality="Be direct.",
        name="Alex",
        calendar_summary="3 events",
        email_summary="5 emails",
        followups="2 stale",
    )
    assert "Calendar" in out
    assert "Email" in out
    assert "3 events" in out
    assert "5 emails" in out
```

`tests/unit/test_summarization.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

from cosinabox.agent.summarization import maybe_summarize


def test_no_summarize_below_threshold() -> None:
    msgs = [{"role": "user", "content": str(i)} for i in range(10)]
    client = MagicMock()
    out = maybe_summarize(msgs, client=client, threshold=25)
    assert out == msgs
    client.messages.create.assert_not_called()


def test_summarize_above_threshold_collapses_old() -> None:
    msgs = [{"role": "user", "content": str(i)} for i in range(30)]
    client = MagicMock()
    fake = MagicMock()
    fake.content = [MagicMock(type="text", text="Summary of older messages.")]
    client.messages.create.return_value = fake
    out = maybe_summarize(msgs, client=client, threshold=25, keep_recent=10)
    assert len(out) == 11  # 1 summary + 10 recent
    assert "Summary of older messages." in out[0]["content"]
```

- [ ] **Step 2: Implement files**

`src/cosinabox/prompts/__init__.py`:

```python
"""Prompt templates with {{personality}} slots."""
```

`src/cosinabox/prompts/core.py`:

```python
"""Core system prompt template."""

from __future__ import annotations

from jinja2 import Template

_SYSTEM_PROMPT = Template(
    """You are {{ name }}'s Chief of Staff.

Timezone: {{ timezone }}

Personality:
{{ personality }}

Be direct. Surface conflicts before they're asked about. If you're confident, act; if not, ask one tight question.
""".strip()
)


def render_system_prompt(*, personality: str, name: str, timezone: str) -> str:
    return _SYSTEM_PROMPT.render(
        personality=personality, name=name, timezone=timezone
    )
```

`src/cosinabox/prompts/briefing.py`:

```python
"""Morning briefing prompt template."""

from __future__ import annotations

from jinja2 import Template

_BRIEFING_PROMPT = Template(
    """Compose {{ name }}'s morning briefing.

Personality:
{{ personality }}

## Calendar
{{ calendar_summary }}

## Email
{{ email_summary }}

## Follow-ups
{{ followups }}

Format the output as a single Telegram message: short, scannable, opinionated. Surface conflicts. Don't recap things {{ name }} already knows.
""".strip()
)


def render_briefing_prompt(
    *,
    personality: str,
    name: str,
    calendar_summary: str,
    email_summary: str,
    followups: str,
) -> str:
    return _BRIEFING_PROMPT.render(
        personality=personality,
        name=name,
        calendar_summary=calendar_summary,
        email_summary=email_summary,
        followups=followups,
    )
```

`src/cosinabox/agent/summarization.py`:

```python
"""Conversation summarization (>25 messages by default).

Layer 1: long contexts degrade quality and burn money.
"""

from __future__ import annotations

from typing import Any

SUMMARIZE_MODEL = "claude-sonnet-4-6"


def maybe_summarize(
    messages: list[dict[str, Any]],
    *,
    client: Any,
    threshold: int = 25,
    keep_recent: int = 10,
) -> list[dict[str, Any]]:
    if len(messages) < threshold:
        return messages
    to_summarize = messages[: len(messages) - keep_recent]
    transcript = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in to_summarize
        if isinstance(m.get("content"), str)
    )
    response = client.messages.create(
        model=SUMMARIZE_MODEL,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    "Summarize the following conversation in <=200 words. "
                    "Preserve names, decisions, and open commitments.\n\n"
                    + transcript
                ),
            }
        ],
    )
    summary_text = "\n".join(b.text for b in response.content if b.type == "text")
    summary_msg = {
        "role": "assistant",
        "content": f"[Earlier conversation summary]\n{summary_text}",
    }
    return [summary_msg, *messages[-keep_recent:]]
```

- [ ] **Step 3: Run tests + commit**

```bash
pytest tests/unit/test_prompts.py tests/unit/test_summarization.py -v
ruff check src/cosinabox/prompts src/cosinabox/agent/summarization.py tests/unit/test_prompts.py tests/unit/test_summarization.py
mypy src/cosinabox/prompts src/cosinabox/agent
git add src/cosinabox/prompts src/cosinabox/agent/summarization.py tests/unit/test_prompts.py tests/unit/test_summarization.py
git commit -m "feat(prompts): core + briefing templates with personality slots, summarization (Plan 1, Task T1.13)"
```

---

### Task T1.14: Run full M1 suite + push the PR

**Est:** 30 min

**Files:** none new — verifies everything from T1.2-T1.13 together.

- [ ] **Step 1: Run the full suite from a clean install**

```bash
cd ~/.worktrees/cosinabox/m1-bootstrap
deactivate 2>/dev/null || true
rm -rf .venv
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,google,fireflies,search]"
ruff check src tests
ruff format --check src tests
mypy src/cosinabox
pytest -q
```

Expected: all tests pass; lint + type-check clean.

- [ ] **Step 2: Push and verify auto-merge wired**

```bash
git push
gh pr view --json statusCheckRollup,mergeable,autoMergeRequest
```

Expected: `autoMergeRequest` is non-null. CI status checks pending or success.

- [ ] **Step 3: Wait for CI to go green and PR to auto-merge**

```bash
gh pr checks --watch
```

When the PR merges, the worktree branch can be deleted:

```bash
cd ~/cosinabox
git fetch origin
git worktree remove ~/.worktrees/cosinabox/m1-bootstrap
git branch -D chore/m1-bootstrap
```

- [ ] **Step 4: Open the M1 retro stub**

```bash
cd ~/cosinabox
git worktree add ~/.worktrees/cosinabox/m1-retro -b docs/m1-retro
cd ~/.worktrees/cosinabox/m1-retro
cp docs/discipline/cosinabox-development-discipline.md /dev/null  # confirm file exists
mkdir -p docs/retros
cp /Users/rovikrobert/Cantina/docs/retros/RETRO_TEMPLATE.md docs/retros/2026-04-XX-cosinabox-m1-retro.md
# Fill in: shipped vs planned, what went well, what slipped, estimate calibration
git add docs/retros
git commit -m "docs(retro): Plan 1 Milestone 1 retro (Plan 1, Task T1.14)"
git push -u origin docs/m1-retro
gh pr create --title "Plan 1 M1 retro" --body "Retro for engine extraction milestone" && gh pr merge --auto --squash --delete-branch
```

The retro must be written within 24 hours of M1 PR merging (per discipline commitment 3).

---

## Milestone 2 — Engine first-run with sample fixture

**Goal:** A fresh user repo can run `cosinabox simulate morning_briefing --fixture=sample` and produce a plausible briefing without ever calling a real Google or Anthropic endpoint. The other 4 jobs are wired up; the scheduler can start; the validator and JSON Schemas are in place.

**Done when:**
- `cosinabox/defaults.py` contains all Layer 1 defaults with comments and dates.
- All 5 built-in jobs exist in `src/cosinabox/jobs/` and have unit tests.
- `src/cosinabox/scheduler/` boots APScheduler with the 5 jobs.
- The `sample` fixture (8 calendar events, 12 emails, 5 stakeholders) lives at `tests/fixtures/sample/`.
- `cosinabox simulate morning_briefing --fixture=sample` returns a non-empty briefing string with mocked Anthropic.
- `cosinabox validate` works against a fresh user repo.
- The JSON Schemas for all 4 user config files exist and are exercised by `validate`.
- Graceful degradation: with `[google]` not installed, `simulate` skips Gmail/Calendar sections rather than crashing.

**PR title:** `Plan 1 Milestone 2: engine first-run`
**PR exit criteria:** All M2 tasks checked; `cosinabox -C tests/fixtures/sample-user-repo simulate morning_briefing --fixture=sample` runs end-to-end with mocked Anthropic; CI green.

---

### Task T2.1: Encode Layer 1 defaults

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/defaults.py`
- Create: `tests/unit/test_defaults.py`

Every operational default from spec Layer 1 is named, given a value, given a date, and given a one-line "why" comment. Business logic must reference `defaults.<NAME>` instead of magic numbers.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_defaults.py`:

```python
from __future__ import annotations

from cosinabox import defaults


def test_cost_caps_present() -> None:
    assert defaults.COST_PER_MESSAGE_CAP_USD == 0.75
    assert defaults.COST_DAILY_CAP_USD == 15.00


def test_tool_loop_limits_present() -> None:
    assert defaults.MAX_TOOL_ITERATIONS == 8
    assert defaults.TOOL_ITERATION_DELAY_S == 2.0


def test_summarization_threshold_present() -> None:
    assert defaults.CONVERSATION_SUMMARIZE_THRESHOLD == 25


def test_pre_meeting_window_present() -> None:
    assert defaults.PRE_MEETING_PREP_MINUTES_BEFORE == 30
    assert defaults.PRE_MEETING_PREP_WINDOW_MINUTES == 5


def test_followup_threshold_present() -> None:
    assert defaults.FOLLOWUP_STALENESS_DAYS == 14


def test_conversation_retention_present() -> None:
    assert defaults.CONVERSATION_RETENTION_DAYS == 30
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_defaults.py -v
```

- [ ] **Step 3: Implement `src/cosinabox/defaults.py`**

```python
"""Encoded operational defaults — every magic number lives here.

Each constant has a comment explaining the lesson and the date it was
chosen, per spec Layer 1. Revisit annually.
"""

from __future__ import annotations

# Cost runaways are real. Per-message + daily caps are forcing functions.
# Chosen 2026-04-11 from cos-agent's empirical spend.
COST_PER_MESSAGE_CAP_USD: float = 0.75
COST_DAILY_CAP_USD: float = 15.00

# Tool loops can blow up if the model keeps calling tools forever.
# 8 is the cos-agent observed median + headroom. (2026-04-11)
MAX_TOOL_ITERATIONS: int = 8

# Anthropic rate limits hit on heavy briefing jobs. 2s between iterations
# kept cos-agent under the limit. (2026-04-11)
TOOL_ITERATION_DELAY_S: float = 2.0

# Long contexts degrade quality and burn money. >25 messages = compress.
# (2026-04-11)
CONVERSATION_SUMMARIZE_THRESHOLD: int = 25
CONVERSATION_SUMMARIZE_KEEP_RECENT: int = 10

# Stale data accumulates. Auto-cleanup after 30 days. (2026-04-11)
CONVERSATION_RETENTION_DAYS: int = 30

# Pre-meeting prep needs a window. Fire when an event is 25-35 min out.
# (2026-04-11)
PRE_MEETING_PREP_MINUTES_BEFORE: int = 30
PRE_MEETING_PREP_WINDOW_MINUTES: int = 5  # ±5 min around minutes_before

# Follow-up staleness threshold. (2026-04-11)
FOLLOWUP_STALENESS_DAYS: int = 14

# Doctor thresholds.
DOCTOR_PERSONALITY_MIN_CHARS: int = 500
DOCTOR_STAKEHOLDERS_MIN_AFTER_DAYS: int = 7
DOCTOR_STAKEHOLDERS_MIN_COUNT: int = 3
DOCTOR_COST_RUNAWAY_RATIO: float = 0.80
DOCTOR_TOOL_LOOP_AVG_THRESHOLD: float = 6.0
DOCTOR_PREP_NOISE_PER_DAY: int = 8
DOCTOR_STALE_FOLLOWUP_COUNT: int = 20
DOCTOR_OAUTH_EXPIRY_WARN_DAYS: int = 14

# Default model IDs (re-exported from agent.routing for convenience).
SONNET_MODEL_ID: str = "claude-sonnet-4-6"
OPUS_MODEL_ID: str = "claude-opus-4-6"
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/unit/test_defaults.py -v
ruff check src/cosinabox/defaults.py tests/unit/test_defaults.py
mypy src/cosinabox/defaults.py
git add src/cosinabox/defaults.py tests/unit/test_defaults.py
git commit -m "feat(defaults): encode Layer 1 operational defaults (Plan 1, Task T2.1)"
```

- [ ] **Step 5: Replace magic numbers in existing modules with `defaults.*`**

```bash
grep -rn '0.75\|15.00\|MAX_TOOL_ITERATIONS\b\|2.0' src/cosinabox/agent/
```

For each hit, replace the literal with `from cosinabox import defaults` + `defaults.NAME`. Re-run the affected unit tests to confirm no regressions. Commit:

```bash
git add src/cosinabox/agent
git commit -m "refactor(agent): use defaults module for caps + delays (Plan 1, Task T2.1)"
```

---

### Task T2.2: APScheduler integration (job base + lifecycle)

**Est:** 2 hr

**Files:**
- Create: `src/cosinabox/scheduler/__init__.py`
- Create: `src/cosinabox/scheduler/runner.py`
- Create: `src/cosinabox/scheduler/lifecycle.py`
- Create: `src/cosinabox/jobs/__init__.py`
- Create: `src/cosinabox/jobs/base.py`
- Create: `tests/unit/test_scheduler.py`
- Create: `tests/integration/test_scheduler.py`
- Reference: `cos-agent/src/scheduler/lifecycle.py`, `cos-agent/src/scheduler/jobs.py`

`Job` is the abstract base for the 5 built-in jobs. `SchedulerRunner` wraps APScheduler with `add_job(job, cron)`, `start()`, `shutdown()`. Each job runs in an **isolated session** (Layer 1: scheduled jobs use isolated session contexts).

- [ ] **Step 1: Write the failing test**

`tests/unit/test_scheduler.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

from cosinabox.jobs.base import Job, JobContext
from cosinabox.scheduler.runner import SchedulerRunner


class _StubJob(Job):
    name = "stub"

    def __init__(self) -> None:
        self.calls = 0

    def run(self, context: JobContext) -> str:
        self.calls += 1
        return "ran"


def test_scheduler_adds_and_runs_job_immediately(monkeypatch) -> None:
    runner = SchedulerRunner(scheduler=MagicMock())
    job = _StubJob()
    runner.add_job(job, cron="0 8 * * *")
    runner.run_now(job.name, context=JobContext(session_id="test"))
    assert job.calls == 1


def test_each_run_uses_unique_session_id() -> None:
    runner = SchedulerRunner(scheduler=MagicMock())
    seen: set[str] = set()

    class CaptureJob(Job):
        name = "capture"

        def run(self, ctx: JobContext) -> str:
            seen.add(ctx.session_id)
            return ""

    job = CaptureJob()
    runner.add_job(job, cron="0 8 * * *")
    runner.run_now(job.name)
    runner.run_now(job.name)
    assert len(seen) == 2
```

- [ ] **Step 2: Implement files**

`src/cosinabox/jobs/__init__.py`:

```python
"""Built-in jobs."""
```

`src/cosinabox/jobs/base.py`:

```python
"""Job base class — every built-in job extends this."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class JobContext:
    session_id: str = field(default_factory=lambda: f"job-{uuid.uuid4().hex[:8]}")
    config: dict = field(default_factory=dict)


class Job(ABC):
    name: str

    @abstractmethod
    def run(self, context: JobContext) -> str:
        """Execute the job. Returns a human-readable result string."""
```

`src/cosinabox/scheduler/__init__.py`:

```python
"""APScheduler-backed job runner."""
```

`src/cosinabox/scheduler/runner.py`:

```python
"""Scheduler runner — wraps APScheduler with cosinabox conventions."""

from __future__ import annotations

from typing import Any

from cosinabox.jobs.base import Job, JobContext


class SchedulerRunner:
    def __init__(self, *, scheduler: Any | None = None) -> None:
        if scheduler is None:
            from apscheduler.schedulers.background import BackgroundScheduler

            scheduler = BackgroundScheduler()
        self._scheduler = scheduler
        self._jobs: dict[str, Job] = {}

    def add_job(self, job: Job, *, cron: str) -> None:
        self._jobs[job.name] = job
        # Real APScheduler call wired only when scheduler is real:
        if hasattr(self._scheduler, "add_job"):
            from apscheduler.triggers.cron import CronTrigger

            self._scheduler.add_job(
                lambda j=job: j.run(JobContext()),
                trigger=CronTrigger.from_crontab(cron),
                id=job.name,
                replace_existing=True,
            )

    def run_now(self, job_name: str, *, context: JobContext | None = None) -> str:
        job = self._jobs[job_name]
        return job.run(context or JobContext())

    def start(self) -> None:
        if hasattr(self._scheduler, "start"):
            self._scheduler.start()

    def shutdown(self) -> None:
        if hasattr(self._scheduler, "shutdown"):
            self._scheduler.shutdown()
```

`src/cosinabox/scheduler/lifecycle.py`:

```python
"""Scheduler lifecycle hooks: install signal handlers, graceful shutdown."""

from __future__ import annotations

import signal
from typing import Callable


def install_shutdown_handler(shutdown: Callable[[], None]) -> None:
    def _handler(signum, frame):  # noqa: ARG001
        shutdown()
    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_scheduler.py -v
ruff check src/cosinabox/scheduler src/cosinabox/jobs tests/unit/test_scheduler.py
mypy src/cosinabox/scheduler src/cosinabox/jobs
git add src/cosinabox/scheduler src/cosinabox/jobs tests/unit/test_scheduler.py
git commit -m "feat(scheduler): runner + Job base + isolated session ids (Plan 1, Task T2.2)"
```

---

### Task T2.3: Built-in job — morning_briefing

**Est:** 3 hr

**Files:**
- Create: `src/cosinabox/jobs/morning_briefing.py`
- Create: `tests/unit/test_jobs_morning_briefing.py`
- Reference: `cos-agent/src/scheduler/briefing_pipeline.py`

`MorningBriefingJob.run(context)` reads calendar + email + follow-ups via the configured tools, composes the briefing prompt, calls the agent loop (or accepts an injected loop in tests), and returns the briefing text. Sends to Telegram only when `context.config["send"]` is true (so simulate mode can dry-run).

- [ ] **Step 1: Write the failing test**

`tests/unit/test_jobs_morning_briefing.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

from cosinabox.jobs.base import JobContext
from cosinabox.jobs.morning_briefing import MorningBriefingJob


def test_briefing_runs_against_stub_tools() -> None:
    gmail = MagicMock()
    gmail.list_recent.return_value = [
        MagicMock(sender="A", subject="X", snippet="..."),
    ]
    cal = MagicMock()
    cal.list_events.return_value = [
        MagicMock(summary="Standup", start=MagicMock(), end=MagicMock()),
    ]
    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "Your morning briefing."
    job = MorningBriefingJob(
        gmail=gmail,
        calendar=cal,
        agent_loop=fake_loop,
        personality="Be direct.",
        name="Alex",
    )
    text = job.run(JobContext())
    assert text == "Your morning briefing."
    fake_loop.run.assert_called_once()


def test_briefing_skips_missing_gmail() -> None:
    cal = MagicMock()
    cal.list_events.return_value = []
    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "No email today."
    job = MorningBriefingJob(
        gmail=None,
        calendar=cal,
        agent_loop=fake_loop,
        personality="Be direct.",
        name="Alex",
    )
    text = job.run(JobContext())
    assert "No email today." in text
```

- [ ] **Step 2: Implement `src/cosinabox/jobs/morning_briefing.py`**

```python
"""Morning briefing job: calendar + email + follow-ups, persona-styled.

Layer 1: graceful degradation — any missing tool means the section is
skipped, not a crash.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from cosinabox.jobs.base import Job, JobContext
from cosinabox.prompts.briefing import render_briefing_prompt


class MorningBriefingJob(Job):
    name = "morning_briefing"

    def __init__(
        self,
        *,
        gmail: Any | None,
        calendar: Any | None,
        agent_loop: Any,
        personality: str,
        name_for_briefing: str = "user",
        followups: str = "(none)",
    ) -> None:
        self.gmail = gmail
        self.calendar = calendar
        self.agent_loop = agent_loop
        self.personality = personality
        self.name_for_briefing = name_for_briefing
        self.followups = followups

    def run(self, context: JobContext) -> str:
        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=12)

        cal_summary = "(calendar not configured)"
        if self.calendar is not None:
            events = self.calendar.list_events(start=now, end=end)
            cal_summary = "\n".join(
                f"- {e.summary}" for e in events
            ) or "(no events today)"

        email_summary = "(email not configured)"
        if self.gmail is not None:
            msgs = self.gmail.list_recent(hours=24, max_results=15)
            email_summary = "\n".join(
                f"- {m.sender}: {m.subject}" for m in msgs
            ) or "(no recent email)"

        prompt = render_briefing_prompt(
            personality=self.personality,
            name=self.name_for_briefing,
            calendar_summary=cal_summary,
            email_summary=email_summary,
            followups=self.followups,
        )
        result = self.agent_loop.run(prompt=prompt, session_id=context.session_id)
        return result.final_text
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_jobs_morning_briefing.py -v
ruff check src/cosinabox/jobs/morning_briefing.py tests/unit/test_jobs_morning_briefing.py
mypy src/cosinabox/jobs/morning_briefing.py
git add src/cosinabox/jobs/morning_briefing.py tests/unit/test_jobs_morning_briefing.py
git commit -m "feat(jobs): morning_briefing with graceful degradation (Plan 1, Task T2.3)"
```

---

### Task T2.4: Built-in job — evening_wrap

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/jobs/evening_wrap.py`
- Create: `tests/unit/test_jobs_evening_wrap.py`

Reads sent mail (last 12 hr) + open commitments (placeholder string until Plan 2's commitment system lands; v0.1 uses a static "(commitments tracking deferred)" line).

- [ ] **Step 1: Write the failing test**

`tests/unit/test_jobs_evening_wrap.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

from cosinabox.jobs.base import JobContext
from cosinabox.jobs.evening_wrap import EveningWrapJob


def test_evening_wrap_runs() -> None:
    gmail = MagicMock()
    gmail.search.return_value = [
        MagicMock(sender="me", subject="Re: thing", snippet="..."),
    ]
    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "Today's wrap."
    job = EveningWrapJob(
        gmail=gmail,
        agent_loop=fake_loop,
        personality="brief",
        name_for_briefing="Alex",
    )
    out = job.run(JobContext())
    assert out == "Today's wrap."


def test_evening_wrap_skips_missing_gmail() -> None:
    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "No mail today."
    job = EveningWrapJob(
        gmail=None,
        agent_loop=fake_loop,
        personality="brief",
        name_for_briefing="Alex",
    )
    assert "No mail today." in job.run(JobContext())
```

- [ ] **Step 2: Implement `src/cosinabox/jobs/evening_wrap.py`**

```python
"""Evening wrap job: sent mail recap + open commitments."""

from __future__ import annotations

from typing import Any

from cosinabox.jobs.base import Job, JobContext
from cosinabox.prompts.briefing import render_briefing_prompt


class EveningWrapJob(Job):
    name = "evening_wrap"

    def __init__(
        self,
        *,
        gmail: Any | None,
        agent_loop: Any,
        personality: str,
        name_for_briefing: str,
    ) -> None:
        self.gmail = gmail
        self.agent_loop = agent_loop
        self.personality = personality
        self.name_for_briefing = name_for_briefing

    def run(self, context: JobContext) -> str:
        sent_summary = "(email not configured)"
        if self.gmail is not None:
            sent = self.gmail.search("from:me newer_than:12h", max_results=20)
            sent_summary = "\n".join(
                f"- {m.subject}" for m in sent
            ) or "(no sent mail in last 12 hours)"
        prompt = render_briefing_prompt(
            personality=self.personality,
            name=self.name_for_briefing,
            calendar_summary="(end of day)",
            email_summary=f"Sent today:\n{sent_summary}",
            followups="(commitments tracking deferred to v0.2)",
        )
        result = self.agent_loop.run(prompt=prompt, session_id=context.session_id)
        return result.final_text
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_jobs_evening_wrap.py -v
ruff check src/cosinabox/jobs/evening_wrap.py tests/unit/test_jobs_evening_wrap.py
mypy src/cosinabox/jobs/evening_wrap.py
git add src/cosinabox/jobs/evening_wrap.py tests/unit/test_jobs_evening_wrap.py
git commit -m "feat(jobs): evening_wrap (Plan 1, Task T2.4)"
```

---

### Task T2.5: Built-in job — pre_meeting_prep

**Est:** 2 hr

**Files:**
- Create: `src/cosinabox/jobs/pre_meeting_prep.py`
- Create: `tests/unit/test_jobs_pre_meeting_prep.py`

Polls every 5 minutes (the default APScheduler cron from spec). On each fire, finds events whose start time is in the window `[now + minutes_before - window, now + minutes_before + window]` (Layer 1 default: 25-35 min ahead). For each event, fetches the attendees, runs a contextualizing prompt, sends one Telegram message per matching event. Skip if event title matches `skip_if_calendar_title_matches` from config.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_jobs_pre_meeting_prep.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from cosinabox.jobs.base import JobContext
from cosinabox.jobs.pre_meeting_prep import PreMeetingPrepJob


def _evt(summary: str, minutes_out: int):
    start = datetime.now(timezone.utc) + timedelta(minutes=minutes_out)
    return MagicMock(
        id=summary, summary=summary, start=start, end=start + timedelta(minutes=30)
    )


def test_fires_only_for_events_in_window() -> None:
    cal = MagicMock()
    cal.list_events.return_value = [
        _evt("Soon", 10),       # too soon
        _evt("Window", 30),     # in window (25-35)
        _evt("Later", 60),      # too far
    ]
    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "prep brief"
    job = PreMeetingPrepJob(
        calendar=cal,
        agent_loop=fake_loop,
        personality="brief",
        minutes_before=30,
        window_minutes=5,
        skip_titles=[],
    )
    msgs = job.run(JobContext())
    assert "Window" in msgs
    assert "Soon" not in msgs


def test_skip_titles_match() -> None:
    cal = MagicMock()
    cal.list_events.return_value = [
        _evt("Lunch", 30),
        _evt("Real Meeting", 30),
    ]
    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "prep"
    job = PreMeetingPrepJob(
        calendar=cal,
        agent_loop=fake_loop,
        personality="brief",
        minutes_before=30,
        window_minutes=5,
        skip_titles=["lunch"],
    )
    out = job.run(JobContext())
    assert "Real Meeting" in out
    assert "Lunch" not in out
```

- [ ] **Step 2: Implement `src/cosinabox/jobs/pre_meeting_prep.py`**

```python
"""Pre-meeting prep job: fires for events 25-35 min out by default.

Layer 1: pre-meeting prep needs a window. Filtering matters.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from cosinabox.jobs.base import Job, JobContext


class PreMeetingPrepJob(Job):
    name = "pre_meeting_prep"

    def __init__(
        self,
        *,
        calendar: Any,
        agent_loop: Any,
        personality: str,
        minutes_before: int = 30,
        window_minutes: int = 5,
        skip_titles: list[str] | None = None,
    ) -> None:
        self.calendar = calendar
        self.agent_loop = agent_loop
        self.personality = personality
        self.minutes_before = minutes_before
        self.window_minutes = window_minutes
        self.skip_titles = [t.lower() for t in (skip_titles or [])]

    def run(self, context: JobContext) -> str:
        if self.calendar is None:
            return "(calendar not configured — pre_meeting_prep is a no-op)"
        now = datetime.now(timezone.utc)
        win_start = now + timedelta(minutes=self.minutes_before - self.window_minutes)
        win_end = now + timedelta(minutes=self.minutes_before + self.window_minutes)
        candidates = self.calendar.list_events(start=win_start, end=win_end)
        outputs: list[str] = []
        for evt in candidates:
            title = (evt.summary or "").lower()
            if any(skip in title for skip in self.skip_titles):
                continue
            prompt = (
                f"Personality:\n{self.personality}\n\n"
                f"Pre-meeting prep for: {evt.summary}\n"
                f"Starts: {evt.start}\n"
                f"Write a 3-line brief: who's in the meeting, recent context, "
                f"one question to ask."
            )
            result = self.agent_loop.run(
                prompt=prompt, session_id=f"{context.session_id}-{evt.id}"
            )
            outputs.append(f"[{evt.summary}] {result.final_text}")
        return "\n".join(outputs) or "(no upcoming meetings in window)"
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_jobs_pre_meeting_prep.py -v
ruff check src/cosinabox/jobs/pre_meeting_prep.py tests/unit/test_jobs_pre_meeting_prep.py
mypy src/cosinabox/jobs/pre_meeting_prep.py
git add src/cosinabox/jobs/pre_meeting_prep.py tests/unit/test_jobs_pre_meeting_prep.py
git commit -m "feat(jobs): pre_meeting_prep with window + skip filters (Plan 1, Task T2.5)"
```

---

### Task T2.6: Built-in job — weekly_review

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/jobs/weekly_review.py`
- Create: `tests/unit/test_jobs_weekly_review.py`

Reads last 7 days of calendar + sent mail + stakeholder activity. Composes a one-page review.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_jobs_weekly_review.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock

from cosinabox.jobs.base import JobContext
from cosinabox.jobs.weekly_review import WeeklyReviewJob


def test_weekly_review_runs() -> None:
    gmail = MagicMock()
    gmail.search.return_value = []
    cal = MagicMock()
    cal.list_events.return_value = []
    fake_loop = MagicMock()
    fake_loop.run.return_value.final_text = "Week recap."
    job = WeeklyReviewJob(
        gmail=gmail,
        calendar=cal,
        agent_loop=fake_loop,
        personality="reflective",
        name_for_briefing="Alex",
    )
    assert job.run(JobContext()) == "Week recap."
```

- [ ] **Step 2: Implement + commit**

`src/cosinabox/jobs/weekly_review.py`:

```python
"""Weekly review job: 7-day calendar + sent mail + relationships recap."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from cosinabox.jobs.base import Job, JobContext


class WeeklyReviewJob(Job):
    name = "weekly_review"

    def __init__(
        self,
        *,
        gmail: Any | None,
        calendar: Any | None,
        agent_loop: Any,
        personality: str,
        name_for_briefing: str,
    ) -> None:
        self.gmail = gmail
        self.calendar = calendar
        self.agent_loop = agent_loop
        self.personality = personality
        self.name_for_briefing = name_for_briefing

    def run(self, context: JobContext) -> str:
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        cal_summary = "(no calendar)"
        if self.calendar is not None:
            events = self.calendar.list_events(start=week_ago, end=now)
            cal_summary = "\n".join(f"- {e.summary}" for e in events) or "(empty week)"
        sent_summary = "(no email)"
        if self.gmail is not None:
            sent = self.gmail.search("from:me newer_than:7d", max_results=50)
            sent_summary = "\n".join(f"- {m.subject}" for m in sent) or "(no sent mail)"
        prompt = (
            f"Personality:\n{self.personality}\n\n"
            f"Compose {self.name_for_briefing}'s weekly review.\n\n"
            f"## Calendar last 7 days\n{cal_summary}\n\n"
            f"## Sent mail last 7 days\n{sent_summary}\n\n"
            f"Surface: themes, missed connections, who didn't get a reply."
        )
        result = self.agent_loop.run(prompt=prompt, session_id=context.session_id)
        return result.final_text
```

```bash
pytest tests/unit/test_jobs_weekly_review.py -v
ruff check src/cosinabox/jobs/weekly_review.py tests/unit/test_jobs_weekly_review.py
mypy src/cosinabox/jobs/weekly_review.py
git add src/cosinabox/jobs/weekly_review.py tests/unit/test_jobs_weekly_review.py
git commit -m "feat(jobs): weekly_review (Plan 1, Task T2.6)"
```

---

### Task T2.7: Built-in job — followup_reminder

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/jobs/followup_reminder.py`
- Create: `tests/unit/test_jobs_followup_reminder.py`

Reads `stakeholders.yaml` and surfaces every stakeholder whose `last_contact` is older than `cadence + FOLLOWUP_STALENESS_DAYS`. Cadence map: `daily=1, weekly=7, biweekly=14, monthly=30, quarterly=90`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_jobs_followup_reminder.py`:

```python
from __future__ import annotations

from datetime import date, timedelta

from cosinabox.jobs.base import JobContext
from cosinabox.jobs.followup_reminder import FollowupReminderJob


def test_surfaces_stale_only() -> None:
    today = date(2026, 4, 12)
    stakeholders = [
        {"name": "Fresh", "cadence": "weekly", "last_contact": (today - timedelta(days=3)).isoformat()},
        {"name": "Stale", "cadence": "weekly", "last_contact": (today - timedelta(days=30)).isoformat()},
        {"name": "Monthly OK", "cadence": "monthly", "last_contact": (today - timedelta(days=20)).isoformat()},
    ]
    job = FollowupReminderJob(stakeholders=stakeholders, today=today)
    out = job.run(JobContext())
    assert "Stale" in out
    assert "Fresh" not in out
    assert "Monthly OK" not in out
```

- [ ] **Step 2: Implement + commit**

`src/cosinabox/jobs/followup_reminder.py`:

```python
"""Followup reminder job — surfaces stale stakeholders.

Layer 1: followup_reminder default threshold = 14 days past cadence.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from cosinabox import defaults
from cosinabox.jobs.base import Job, JobContext

CADENCE_DAYS = {
    "daily": 1,
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
    "quarterly": 90,
}


class FollowupReminderJob(Job):
    name = "followup_reminder"

    def __init__(
        self,
        *,
        stakeholders: list[dict[str, Any]],
        today: date | None = None,
        staleness_days: int = defaults.FOLLOWUP_STALENESS_DAYS,
    ) -> None:
        self.stakeholders = stakeholders
        self.today = today or datetime.utcnow().date()
        self.staleness_days = staleness_days

    def run(self, context: JobContext) -> str:  # noqa: ARG002
        stale: list[str] = []
        for s in self.stakeholders:
            cadence = CADENCE_DAYS.get(s.get("cadence", "weekly"), 7)
            last = date.fromisoformat(s["last_contact"])
            days_since = (self.today - last).days
            if days_since > cadence + self.staleness_days:
                stale.append(f"- {s['name']} ({days_since}d since contact)")
        if not stale:
            return "(no stale follow-ups)"
        return "Stale follow-ups:\n" + "\n".join(stale)
```

```bash
pytest tests/unit/test_jobs_followup_reminder.py -v
ruff check src/cosinabox/jobs/followup_reminder.py tests/unit/test_jobs_followup_reminder.py
mypy src/cosinabox/jobs/followup_reminder.py
git add src/cosinabox/jobs/followup_reminder.py tests/unit/test_jobs_followup_reminder.py
git commit -m "feat(jobs): followup_reminder (Plan 1, Task T2.7)"
```

---

### Task T2.8: Persona template — founder

**Est:** 30 min

**Files:**
- Create: `src/cosinabox/personas/founder.md`
- Create: `tests/unit/test_personas.py`

The single v0.1 persona template. Loaded by `cosinabox set-persona --role founder` (T4.6). Markdown with frontmatter and example sections; users overwrite with their own content during the interview.

- [ ] **Step 1: Write the persona file**

`src/cosinabox/personas/founder.md`:

```markdown
---
schema_version: 1
name: <YOUR NAME>
role: Founder of <YOUR COMPANY>
timezone: <YOUR_TIMEZONE>
---

# Voice
You are my Chief of Staff. Be direct. Skip the throat-clearing. Cut anything that isn't load-bearing.

# Stakes
<Replace this paragraph with the most important thing happening in your work over the next 6 weeks. A CoS without stakes is a chatbot.>

# Defaults
- Default to bullets, not paragraphs
- Surface conflicts before I ask
- If you're confident, act; if not, ask one tight question
- Use my timezone for all times
```

- [ ] **Step 2: Write the test**

`tests/unit/test_personas.py`:

```python
from __future__ import annotations

from importlib.resources import files


def test_founder_persona_has_required_sections() -> None:
    text = files("cosinabox.personas").joinpath("founder.md").read_text()
    assert "schema_version: 1" in text
    assert "# Voice" in text
    assert "# Stakes" in text
    assert "# Defaults" in text
```

- [ ] **Step 3: Wire `cosinabox.personas` as a package + commit**

```bash
mkdir -p src/cosinabox/personas
touch src/cosinabox/personas/__init__.py
# (founder.md already created in step 1)
pytest tests/unit/test_personas.py -v
git add src/cosinabox/personas tests/unit/test_personas.py
git commit -m "feat(personas): founder template (Plan 1, Task T2.8)"
```

Update `pyproject.toml` to include the markdown file in the wheel:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/cosinabox"]

[tool.hatch.build.targets.wheel.force-include]
"src/cosinabox/personas/founder.md" = "cosinabox/personas/founder.md"
```

```bash
git add pyproject.toml
git commit -m "build: include persona markdown in wheel (Plan 1, Task T2.8)"
```

---

### Task T2.9: Sample fixture (8 events, 12 emails, 5 stakeholders)

**Est:** 2 hr

**Files:**
- Create: `tests/fixtures/sample/calendar_events.json`
- Create: `tests/fixtures/sample/emails.json`
- Create: `tests/fixtures/sample/stakeholders.yaml`
- Create: `tests/fixtures/sample/personality.md`
- Create: `tests/fixtures/sample/jobs.yaml`
- Create: `tests/fixtures/sample/integrations.yaml`
- Create: `tests/unit/test_sample_fixture.py`

This fixture is the **canonical input for `cosinabox simulate`**. It must exercise every code path in `morning_briefing`: at least one event with a conflict, at least one event with attendees, at least one stale follow-up, at least one email from a stakeholder, at least one email from a stranger.

- [ ] **Step 1: Write `calendar_events.json` (8 events)**

```json
[
  {"id": "e1", "summary": "Standup", "start": "2026-04-13T09:00:00+00:00", "end": "2026-04-13T09:15:00+00:00", "attendees": ["alex@loop.ai", "david@loop.ai"]},
  {"id": "e2", "summary": "Investor sync — Sequoia", "start": "2026-04-13T10:00:00+00:00", "end": "2026-04-13T10:30:00+00:00", "attendees": ["sarah@sequoia.com"]},
  {"id": "e3", "summary": "Lunch", "start": "2026-04-13T12:00:00+00:00", "end": "2026-04-13T13:00:00+00:00", "attendees": []},
  {"id": "e4", "summary": "Conflict A", "start": "2026-04-13T14:00:00+00:00", "end": "2026-04-13T14:30:00+00:00", "attendees": ["jamie@loop.ai"]},
  {"id": "e5", "summary": "Conflict B (overlaps A)", "start": "2026-04-13T14:15:00+00:00", "end": "2026-04-13T14:45:00+00:00", "attendees": ["mira@partner.co"]},
  {"id": "e6", "summary": "1:1 with David", "start": "2026-04-13T15:00:00+00:00", "end": "2026-04-13T15:30:00+00:00", "attendees": ["david@loop.ai"]},
  {"id": "e7", "summary": "Hiring loop debrief", "start": "2026-04-13T16:00:00+00:00", "end": "2026-04-13T17:00:00+00:00", "attendees": ["recruiter@search.io", "david@loop.ai"]},
  {"id": "e8", "summary": "Focus block", "start": "2026-04-13T17:30:00+00:00", "end": "2026-04-13T18:30:00+00:00", "attendees": []}
]
```

- [ ] **Step 2: Write `emails.json` (12 emails)**

```json
[
  {"id": "m1", "sender": "Sarah Chen <sarah@sequoia.com>", "subject": "Re: Q2 metrics update", "snippet": "Looks great. Can you confirm runway?", "date": "2026-04-12T22:30:00+00:00"},
  {"id": "m2", "sender": "David Park <david@loop.ai>", "subject": "Hiring update", "snippet": "Two strong candidates this week.", "date": "2026-04-12T21:00:00+00:00"},
  {"id": "m3", "sender": "Acme Procurement <noreply@acme.com>", "subject": "Your invoice is ready", "snippet": "PDF attached.", "date": "2026-04-12T19:45:00+00:00"},
  {"id": "m4", "sender": "Recruiter <recruiter@search.io>", "subject": "Loop interview debrief", "snippet": "Notes attached, see you tomorrow.", "date": "2026-04-12T18:30:00+00:00"},
  {"id": "m5", "sender": "Jamie Kim <jamie@loop.ai>", "subject": "Roadmap question", "snippet": "Quick clarification on Q3 priorities.", "date": "2026-04-12T17:00:00+00:00"},
  {"id": "m6", "sender": "Mira Allen <mira@partner.co>", "subject": "Partnership next steps", "snippet": "Want to lock in next meeting.", "date": "2026-04-12T16:00:00+00:00"},
  {"id": "m7", "sender": "Stripe <updates@stripe.com>", "subject": "Your subscription renews", "snippet": "Renewal in 5 days.", "date": "2026-04-12T15:00:00+00:00"},
  {"id": "m8", "sender": "Calendly <no-reply@calendly.com>", "subject": "New booking", "snippet": "Booked for Friday 4pm.", "date": "2026-04-12T14:30:00+00:00"},
  {"id": "m9", "sender": "Alice Doe <alice@randomcorp.com>", "subject": "Cold intro request", "snippet": "Hi, would love 15 min...", "date": "2026-04-12T13:00:00+00:00"},
  {"id": "m10", "sender": "GitHub <notifications@github.com>", "subject": "[loop-ai/api] PR #123 merged", "snippet": "Merged.", "date": "2026-04-12T11:00:00+00:00"},
  {"id": "m11", "sender": "Linear <notifications@linear.app>", "subject": "Sprint summary", "snippet": "12 issues completed.", "date": "2026-04-12T10:00:00+00:00"},
  {"id": "m12", "sender": "Sarah Chen <sarah@sequoia.com>", "subject": "Board pre-read", "snippet": "Sending board pre-read tomorrow.", "date": "2026-04-12T09:00:00+00:00"}
]
```

- [ ] **Step 3: Write `stakeholders.yaml`**

```yaml
schema_version: 1
stakeholders:
  - name: Sarah Chen
    role: Lead investor (Sequoia)
    cadence: weekly
    last_contact: "2026-04-08"
    notes: Wants monthly metric updates. Replies fastest in mornings.
  - name: David Park
    role: Co-founder
    cadence: daily
    last_contact: "2026-04-12"
    notes: We sync constantly — don't surface 1:1s.
  - name: Jamie Kim
    role: Head of product
    cadence: weekly
    last_contact: "2026-03-20"   # stale
    notes: Owns Q3 roadmap.
  - name: Mira Allen
    role: Strategic partner contact at Partner Co
    cadence: biweekly
    last_contact: "2026-04-01"
    notes: Slow to reply but high-signal.
  - name: Alex's Mom
    role: Family
    cadence: weekly
    last_contact: "2026-03-15"   # very stale
    notes: Call her.
```

- [ ] **Step 4: Write `personality.md`**

```markdown
---
schema_version: 1
name: Alex
role: Founder of Loop AI
timezone: America/Los_Angeles
---

# Voice
You are my Chief of Staff. Be direct. Skip the throat-clearing.

# Stakes
We're 6 weeks from a Series A close. Every conversation is either moving us toward signed term sheets or it isn't.

# Defaults
- Default to bullets, not paragraphs
- Surface conflicts before I ask
- Use Pacific time
```

- [ ] **Step 5: Write `jobs.yaml`**

```yaml
schema_version: 1
jobs:
  morning_briefing:
    enabled: true
    schedule: "0 8 * * *"
    timezone: America/Los_Angeles
  evening_wrap:
    enabled: true
    schedule: "0 18 * * *"
  pre_meeting_prep:
    enabled: true
    minutes_before: 30
    skip_if_calendar_title_matches: ["focus block", "lunch"]
  weekly_review:
    enabled: true
    schedule: "0 16 * * 5"
  followup_reminder:
    enabled: false
```

- [ ] **Step 6: Write `integrations.yaml`**

```yaml
schema_version: 1
integrations:
  google:
    enabled: true
    accounts:
      - email: alex@loop.ai
        scopes: [gmail, calendar]
  fireflies:
    enabled: false
  web_search:
    enabled: false
```

- [ ] **Step 7: Write the fixture self-test**

`tests/unit/test_sample_fixture.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import yaml

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample"


def test_calendar_has_8_events_with_conflict() -> None:
    events = json.loads((FIXTURE / "calendar_events.json").read_text())
    assert len(events) == 8
    summaries = {e["summary"] for e in events}
    assert "Conflict A" in summaries
    assert "Conflict B (overlaps A)" in summaries


def test_emails_has_12() -> None:
    msgs = json.loads((FIXTURE / "emails.json").read_text())
    assert len(msgs) == 12


def test_stakeholders_has_5() -> None:
    data = yaml.safe_load((FIXTURE / "stakeholders.yaml").read_text())
    assert len(data["stakeholders"]) == 5


def test_personality_has_stakes() -> None:
    text = (FIXTURE / "personality.md").read_text()
    assert "Stakes" in text
```

- [ ] **Step 8: Run + commit**

```bash
pytest tests/unit/test_sample_fixture.py -v
git add tests/fixtures/sample tests/unit/test_sample_fixture.py
git commit -m "feat(fixtures): sample user-repo fixture for simulate (Plan 1, Task T2.9)"
```

---

### Task T2.10: JSON Schemas for the 4 user config files

**Est:** 2 hr

**Files:**
- Create: `src/cosinabox/schemas/personality.schema.json`
- Create: `src/cosinabox/schemas/stakeholders.schema.json`
- Create: `src/cosinabox/schemas/jobs.schema.json`
- Create: `src/cosinabox/schemas/integrations.schema.json`
- Create: `src/cosinabox/schemas/__init__.py`
- Create: `tests/unit/test_schemas.py`

Each schema validates the canonical user config file. `personality.md` is mostly free-form markdown, so its schema only validates the YAML frontmatter (loaded separately by the validator).

- [ ] **Step 1: Write `personality.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "personality.md frontmatter",
  "type": "object",
  "required": ["schema_version", "name", "timezone"],
  "properties": {
    "schema_version": {"const": 1},
    "name": {"type": "string", "minLength": 1},
    "role": {"type": "string"},
    "timezone": {"type": "string", "minLength": 1}
  }
}
```

- [ ] **Step 2: Write `stakeholders.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "stakeholders.yaml",
  "type": "object",
  "required": ["schema_version", "stakeholders"],
  "properties": {
    "schema_version": {"const": 1},
    "stakeholders": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "cadence"],
        "properties": {
          "name": {"type": "string"},
          "role": {"type": "string"},
          "cadence": {"enum": ["daily", "weekly", "biweekly", "monthly", "quarterly"]},
          "last_contact": {"type": "string", "format": "date"},
          "notes": {"type": "string"}
        }
      }
    }
  }
}
```

- [ ] **Step 3: Write `jobs.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "jobs.yaml",
  "type": "object",
  "required": ["schema_version", "jobs"],
  "properties": {
    "schema_version": {"const": 1},
    "jobs": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "required": ["enabled"],
        "properties": {
          "enabled": {"type": "boolean"},
          "schedule": {"type": "string"},
          "timezone": {"type": "string"},
          "minutes_before": {"type": "integer", "minimum": 5},
          "skip_if_calendar_title_matches": {
            "type": "array",
            "items": {"type": "string"}
          }
        }
      }
    }
  }
}
```

- [ ] **Step 4: Write `integrations.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "integrations.yaml",
  "type": "object",
  "required": ["schema_version", "integrations"],
  "properties": {
    "schema_version": {"const": 1},
    "integrations": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "required": ["enabled"],
        "properties": {
          "enabled": {"type": "boolean"},
          "accounts": {"type": "array"}
        }
      }
    }
  }
}
```

- [ ] **Step 5: Write the test**

`src/cosinabox/schemas/__init__.py`:

```python
"""JSON Schemas for user config files."""

from __future__ import annotations

import json
from importlib.resources import files

SCHEMA_NAMES = ("personality", "stakeholders", "jobs", "integrations")


def load_schema(name: str) -> dict:
    raw = files("cosinabox.schemas").joinpath(f"{name}.schema.json").read_text()
    return json.loads(raw)
```

`tests/unit/test_schemas.py`:

```python
from __future__ import annotations

import pytest
from jsonschema import ValidationError, validate

from cosinabox.schemas import SCHEMA_NAMES, load_schema


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_schema_loads(name: str) -> None:
    schema = load_schema(name)
    assert schema["$schema"].startswith("https://json-schema.org")


def test_stakeholders_valid() -> None:
    schema = load_schema("stakeholders")
    validate(
        instance={
            "schema_version": 1,
            "stakeholders": [
                {"name": "X", "cadence": "weekly", "last_contact": "2026-01-01"}
            ],
        },
        schema=schema,
    )


def test_stakeholders_invalid_cadence() -> None:
    schema = load_schema("stakeholders")
    with pytest.raises(ValidationError):
        validate(
            instance={
                "schema_version": 1,
                "stakeholders": [{"name": "X", "cadence": "yearly"}],
            },
            schema=schema,
        )


def test_jobs_valid() -> None:
    schema = load_schema("jobs")
    validate(
        instance={
            "schema_version": 1,
            "jobs": {"morning_briefing": {"enabled": True, "schedule": "0 8 * * *"}},
        },
        schema=schema,
    )
```

- [ ] **Step 6: Update pyproject.toml to include schemas in wheel**

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/cosinabox/personas/founder.md" = "cosinabox/personas/founder.md"
"src/cosinabox/schemas/personality.schema.json" = "cosinabox/schemas/personality.schema.json"
"src/cosinabox/schemas/stakeholders.schema.json" = "cosinabox/schemas/stakeholders.schema.json"
"src/cosinabox/schemas/jobs.schema.json" = "cosinabox/schemas/jobs.schema.json"
"src/cosinabox/schemas/integrations.schema.json" = "cosinabox/schemas/integrations.schema.json"
```

- [ ] **Step 7: Run + commit**

```bash
pytest tests/unit/test_schemas.py -v
ruff check src/cosinabox/schemas tests/unit/test_schemas.py
mypy src/cosinabox/schemas
git add src/cosinabox/schemas tests/unit/test_schemas.py pyproject.toml
git commit -m "feat(schemas): JSON Schemas for the 4 user config files (Plan 1, Task T2.10)"
```

---

### Task T2.11: `cosinabox validate` command

**Est:** 2 hr

**Files:**
- Create: `src/cosinabox/cli/validate.py`
- Modify: `src/cosinabox/cli/main.py` (register `validate` command)
- Create: `tests/unit/test_cli_validate.py`

`cosinabox -C <dir> validate` walks the 4 config files in `<dir>`, validates each against its schema, prints PASS/FAIL per file with line + column on failure. `-C/--config-dir` defaults to `os.getenv("COSINABOX_CONFIG_DIR", os.getcwd())`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_cli_validate.py`:

```python
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli


def _write_valid_repo(tmp: Path) -> None:
    (tmp / "personality.md").write_text(
        "---\nschema_version: 1\nname: Alex\ntimezone: America/Los_Angeles\n---\n\n# Voice\nbe direct.\n"
    )
    (tmp / "stakeholders.yaml").write_text(
        "schema_version: 1\nstakeholders:\n  - name: X\n    cadence: weekly\n"
    )
    (tmp / "jobs.yaml").write_text(
        'schema_version: 1\njobs:\n  morning_briefing:\n    enabled: true\n    schedule: "0 8 * * *"\n'
    )
    (tmp / "integrations.yaml").write_text(
        "schema_version: 1\nintegrations:\n  google:\n    enabled: false\n"
    )


def test_validate_passes_for_clean_repo(tmp_path: Path) -> None:
    _write_valid_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "validate"])
    assert result.exit_code == 0
    assert "personality.md PASS" in result.output
    assert "stakeholders.yaml PASS" in result.output


def test_validate_fails_on_bad_cadence(tmp_path: Path) -> None:
    _write_valid_repo(tmp_path)
    (tmp_path / "stakeholders.yaml").write_text(
        "schema_version: 1\nstakeholders:\n  - name: X\n    cadence: yearly\n"
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "validate"])
    assert result.exit_code != 0
    assert "stakeholders.yaml FAIL" in result.output
```

- [ ] **Step 2: Implement files**

`src/cosinabox/cli/validate.py`:

```python
"""`cosinabox validate` — schema-check all user config files."""

from __future__ import annotations

import json
import re
from pathlib import Path

import click
import yaml
from jsonschema import ValidationError, validate

from cosinabox.schemas import load_schema

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def _load_personality_frontmatter(path: Path) -> dict:
    text = path.read_text()
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("personality.md missing YAML frontmatter")
    return yaml.safe_load(m.group(1))


def _validate_one(
    config_dir: Path, filename: str, schema_name: str, loader
) -> tuple[bool, str]:
    path = config_dir / filename
    if not path.exists():
        return False, f"{filename} MISSING"
    try:
        instance = loader(path)
        validate(instance=instance, schema=load_schema(schema_name))
        return True, f"{filename} PASS"
    except ValidationError as e:
        return False, f"{filename} FAIL: {e.message}"
    except Exception as e:
        return False, f"{filename} FAIL: {e}"


@click.command("validate")
@click.option("--json", "json_out", is_flag=True, help="Output results as JSON.")
@click.pass_context
def validate_cmd(ctx: click.Context, json_out: bool) -> None:
    """Schema-check all user config files."""
    config_dir: Path = ctx.obj["config_dir"]
    targets = [
        ("personality.md", "personality", _load_personality_frontmatter),
        ("stakeholders.yaml", "stakeholders", lambda p: yaml.safe_load(p.read_text())),
        ("jobs.yaml", "jobs", lambda p: yaml.safe_load(p.read_text())),
        ("integrations.yaml", "integrations", lambda p: yaml.safe_load(p.read_text())),
    ]
    results = [_validate_one(config_dir, *t) for t in targets]
    if json_out:
        click.echo(json.dumps([{"file": r[1].split()[0], "ok": r[0], "msg": r[1]} for r in results], indent=2))
    else:
        for ok, msg in results:
            click.echo(msg)
    if not all(ok for ok, _ in results):
        ctx.exit(1)
```

`src/cosinabox/cli/main.py` (replace existing):

```python
"""cosinabox CLI entry point."""

from __future__ import annotations

import os
from pathlib import Path

import click

from cosinabox.cli.validate import validate_cmd


@click.group()
@click.option(
    "-C",
    "--config-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=lambda: Path(os.getenv("COSINABOX_CONFIG_DIR", os.getcwd())),
    help="User repo config directory.",
)
@click.version_option()
@click.pass_context
def cli(ctx: click.Context, config_dir: Path) -> None:
    """CoSinaBox — open-source Chief of Staff."""
    ctx.ensure_object(dict)
    ctx.obj["config_dir"] = config_dir


cli.add_command(validate_cmd)


if __name__ == "__main__":
    cli()
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_cli_validate.py -v
ruff check src/cosinabox/cli tests/unit/test_cli_validate.py
mypy src/cosinabox/cli
git add src/cosinabox/cli tests/unit/test_cli_validate.py
git commit -m "feat(cli): cosinabox validate command (Plan 1, Task T2.11)"
```

---

### Task T2.12: Sample-user-repo fixture for the CLI

**Est:** 30 min

**Files:**
- Create: `tests/fixtures/sample-user-repo/personality.md` (copy from `tests/fixtures/sample/personality.md`)
- Create: `tests/fixtures/sample-user-repo/stakeholders.yaml` (copy)
- Create: `tests/fixtures/sample-user-repo/jobs.yaml` (copy)
- Create: `tests/fixtures/sample-user-repo/integrations.yaml` (copy)

A second fixture directory shaped like a real user repo. Tests for `simulate`, `validate`, `describe`, and `doctor` invoke the CLI with `-C tests/fixtures/sample-user-repo`.

- [ ] **Step 1: Copy fixture files**

```bash
mkdir -p tests/fixtures/sample-user-repo
cp tests/fixtures/sample/personality.md tests/fixtures/sample-user-repo/
cp tests/fixtures/sample/stakeholders.yaml tests/fixtures/sample-user-repo/
cp tests/fixtures/sample/jobs.yaml tests/fixtures/sample-user-repo/
cp tests/fixtures/sample/integrations.yaml tests/fixtures/sample-user-repo/
```

- [ ] **Step 2: Smoke test the CLI against it**

```bash
cosinabox -C tests/fixtures/sample-user-repo validate
```

Expected: all 4 files PASS, exit 0.

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/sample-user-repo
git commit -m "chore(fixtures): sample-user-repo for CLI smoke tests (Plan 1, Task T2.12)"
```

---

### Task T2.13: `cosinabox simulate <job> --fixture=sample`

**Est:** 2 hr

**Files:**
- Create: `src/cosinabox/cli/simulate.py`
- Modify: `src/cosinabox/cli/main.py` (register `simulate`)
- Create: `tests/integration/test_cli_simulate.py`

The simulate command:
1. Loads the user config from `-C <dir>`.
2. Loads fixture data from `tests/fixtures/<fixture>/` (so `--fixture=sample` reads from `tests/fixtures/sample/`).
3. Builds stub gmail + calendar tools that return the fixture data.
4. Builds an AgentLoop that uses a **real Anthropic client if `ANTHROPIC_API_KEY` is set**, otherwise a mocked client that returns canned text. (For CI, use the mock; for local user dry-run, use the real key.)
5. Runs the requested job and prints the result.

- [ ] **Step 1: Write the failing test**

`tests/integration/test_cli_simulate.py`:

```python
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
USER_REPO = REPO_ROOT / "tests" / "fixtures" / "sample-user-repo"


def test_simulate_morning_briefing_with_mocked_anthropic(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["-C", str(USER_REPO), "simulate", "morning_briefing", "--fixture=sample"],
    )
    assert result.exit_code == 0
    assert "morning_briefing" in result.output.lower() or "Briefing" in result.output
```

- [ ] **Step 2: Implement `src/cosinabox/cli/simulate.py`**

```python
"""`cosinabox simulate <job>` — local dry-run against a fixture."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import click
import yaml

from cosinabox import defaults
from cosinabox.agent.cost import CostTracker
from cosinabox.agent.loop import AgentLoop
from cosinabox.agent.routing import Router
from cosinabox.jobs.base import JobContext
from cosinabox.jobs.evening_wrap import EveningWrapJob
from cosinabox.jobs.followup_reminder import FollowupReminderJob
from cosinabox.jobs.morning_briefing import MorningBriefingJob
from cosinabox.jobs.pre_meeting_prep import PreMeetingPrepJob
from cosinabox.jobs.weekly_review import WeeklyReviewJob

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures"


@dataclass
class _StubMessage:
    id: str
    sender: str
    subject: str
    snippet: str
    date: str


@dataclass
class _StubEvent:
    id: str
    summary: str
    start: datetime
    end: datetime


class _StubGmail:
    def __init__(self, messages: list[_StubMessage]) -> None:
        self._msgs = messages

    def list_recent(self, *, hours: int = 24, max_results: int = 25) -> list[_StubMessage]:  # noqa: ARG002
        return self._msgs[:max_results]

    def search(self, query: str, *, max_results: int = 25) -> list[_StubMessage]:  # noqa: ARG002
        return self._msgs[:max_results]


class _StubCalendar:
    def __init__(self, events: list[_StubEvent]) -> None:
        self._events = events

    def list_events(self, *, start: datetime, end: datetime) -> list[_StubEvent]:  # noqa: ARG002
        return self._events


def _load_fixture(fixture: str) -> tuple[_StubGmail, _StubCalendar, list[dict]]:
    fdir = FIXTURE_ROOT / fixture
    msgs_raw = json.loads((fdir / "emails.json").read_text())
    events_raw = json.loads((fdir / "calendar_events.json").read_text())
    stakeholders = yaml.safe_load((fdir / "stakeholders.yaml").read_text())["stakeholders"]
    msgs = [_StubMessage(**m) for m in msgs_raw]
    events = [
        _StubEvent(
            id=e["id"],
            summary=e["summary"],
            start=datetime.fromisoformat(e["start"]),
            end=datetime.fromisoformat(e["end"]),
        )
        for e in events_raw
    ]
    return _StubGmail(msgs), _StubCalendar(events), stakeholders


def _build_agent_loop() -> AgentLoop:
    if os.getenv("ANTHROPIC_API_KEY"):
        from anthropic import Anthropic

        client: Any = Anthropic()
    else:
        client = MagicMock()
        fake_resp = MagicMock()
        fake_resp.stop_reason = "end_turn"
        fake_resp.content = [MagicMock(type="text", text="[mocked briefing output]")]
        fake_resp.usage.input_tokens = 0
        fake_resp.usage.output_tokens = 0
        client.messages.create.return_value = fake_resp
    return AgentLoop(
        anthropic_client=client,
        router=Router(),
        cost_tracker=CostTracker(
            per_message_cap_usd=defaults.COST_PER_MESSAGE_CAP_USD,
            daily_cap_usd=defaults.COST_DAILY_CAP_USD,
        ),
        tools={},
        max_tool_iterations=defaults.MAX_TOOL_ITERATIONS,
        tool_iteration_delay_s=0,  # no sleep in simulate
    )


def _load_personality(config_dir: Path) -> tuple[str, str]:
    text = (config_dir / "personality.md").read_text()
    import re

    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return "(no personality)", "user"
    front = yaml.safe_load(m.group(1))
    body = m.group(2)
    return body, front.get("name", "user")


@click.command("simulate")
@click.argument("job_name")
@click.option("--fixture", default="sample", help="Fixture name under tests/fixtures/.")
@click.pass_context
def simulate_cmd(ctx: click.Context, job_name: str, fixture: str) -> None:
    """Run a job against a fixture and print what would be sent."""
    config_dir: Path = ctx.obj["config_dir"]
    gmail, calendar, stakeholders = _load_fixture(fixture)
    personality, name = _load_personality(config_dir)
    loop = _build_agent_loop()

    job: Any
    if job_name == "morning_briefing":
        job = MorningBriefingJob(
            gmail=gmail, calendar=calendar, agent_loop=loop,
            personality=personality, name_for_briefing=name,
        )
    elif job_name == "evening_wrap":
        job = EveningWrapJob(
            gmail=gmail, agent_loop=loop, personality=personality, name_for_briefing=name,
        )
    elif job_name == "pre_meeting_prep":
        job = PreMeetingPrepJob(
            calendar=calendar, agent_loop=loop, personality=personality,
        )
    elif job_name == "weekly_review":
        job = WeeklyReviewJob(
            gmail=gmail, calendar=calendar, agent_loop=loop,
            personality=personality, name_for_briefing=name,
        )
    elif job_name == "followup_reminder":
        job = FollowupReminderJob(stakeholders=stakeholders)
    else:
        raise click.UsageError(f"Unknown job: {job_name}")

    result = job.run(JobContext(session_id=f"simulate-{job_name}"))
    click.echo(f"=== Simulated {job_name} ===")
    click.echo(result)
```

Register in `cli/main.py`:

```python
from cosinabox.cli.simulate import simulate_cmd
cli.add_command(simulate_cmd)
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/integration/test_cli_simulate.py -v
ruff check src/cosinabox/cli tests/integration/test_cli_simulate.py
mypy src/cosinabox/cli
git add src/cosinabox/cli/simulate.py src/cosinabox/cli/main.py tests/integration/test_cli_simulate.py
git commit -m "feat(cli): cosinabox simulate <job> --fixture (Plan 1, Task T2.13)"
```

---

### Task T2.14: Run M2 suite + open M2 PR

**Est:** 30 min

- [ ] **Step 1: Full M2 verification**

```bash
cd ~/.worktrees/cosinabox/m1-bootstrap  # or wherever M2 work happened
ruff check src tests
ruff format --check src tests
mypy src/cosinabox
pytest -q
```

Expected: clean. The simulate integration test runs against the mocked Anthropic client.

- [ ] **Step 2: Push, PR, auto-merge**

```bash
git push
gh pr create --title "Plan 1 Milestone 2: engine first-run" --body "$(cat <<'EOF'
## Summary
Wires up the 5 built-in jobs, the JSON Schemas, the validate + simulate CLI commands, and the sample fixture. After this milestone, a fresh user repo can dry-run morning_briefing locally without real API credentials.

## Test plan
- [ ] All M2 unit + integration tests pass
- [ ] `cosinabox -C tests/fixtures/sample-user-repo simulate morning_briefing --fixture=sample` returns non-empty output
- [ ] `cosinabox -C tests/fixtures/sample-user-repo validate` returns exit 0
EOF
)"
gh pr merge --auto --squash --delete-branch
```

- [ ] **Step 3: Write M2 retro after merge**

Same pattern as T1.14 step 4. Date the file and write within 24 hours.

---

## Milestone 3 — User repo template + CLAUDE.md + sub-docs

**Goal:** A complete `templates/user-repo/` scaffold inside the cosinabox engine that `cosinabox init` can copy. The scaffold contains every file an end-user needs to start an interview with Claude Code: empty config files, CLAUDE.md as an index, six sub-docs in `docs/agent/`, BEST_PRACTICES.md, .gitignore, and the pre-commit hook with secret scanning + validation.

**Done when:**
- `src/cosinabox/templates/user-repo/` directory exists with all listed files.
- `cosinabox init <dir>` copies the scaffold and prints the "open in Claude Code" message.
- `cosinabox init` is idempotent on a non-empty directory (errors loudly rather than overwriting).
- A scaffolded user repo passes `cosinabox -C <dir> validate` out of the box (with a stub stakeholder so the schema is satisfied).
- The pre-commit hook in the user-repo template runs `cosinabox validate` + a secret scan and rejects commits that fail.

**PR title:** `Plan 1 Milestone 3: user repo template + agent docs`
**PR exit criteria:** All M3 tasks checked; `cosinabox init /tmp/test-cos && cosinabox -C /tmp/test-cos validate` returns exit 0; CI green.

---

### Task T3.1: Empty config file scaffolds

**Est:** 30 min

**Files (all in `src/cosinabox/templates/user-repo/`):**
- Create: `personality.md`
- Create: `stakeholders.yaml`
- Create: `jobs.yaml`
- Create: `integrations.yaml`
- Create: `.env.example`

These are the files a user edits. Each has the schema_version field and minimum-viable content so a fresh `cosinabox validate` passes immediately after `cosinabox init`.

- [ ] **Step 1: Write `personality.md`**

```markdown
---
schema_version: 1
name: <YOUR NAME>
role: <YOUR ROLE>
timezone: <e.g. America/Los_Angeles>
---

# Voice
<Tell your CoS how to talk to you. Direct? Warm? Analytical? See docs/agent/persona-interview.md to walk through this with Claude Code.>

# Stakes
<The most important thing happening in your work over the next 6 weeks. A CoS without stakes is a chatbot.>

# Defaults
- <List any opinions you want enforced — output format, when to ask vs act, etc.>
```

- [ ] **Step 2: Write `stakeholders.yaml`**

```yaml
schema_version: 1
stakeholders:
  - name: Example Stakeholder (replace me)
    role: Set this to a real role
    cadence: weekly
    last_contact: "2026-01-01"
    notes: |
      Edit or delete this entry. Walk through docs/agent/persona-interview.md
      with Claude Code to fill in your top 5 stakeholders.
```

- [ ] **Step 3: Write `jobs.yaml`**

```yaml
schema_version: 1
jobs:
  morning_briefing:
    enabled: true
    schedule: "0 8 * * *"
    timezone: <YOUR_TIMEZONE>
  pre_meeting_prep:
    enabled: true
    minutes_before: 30
    skip_if_calendar_title_matches: ["focus block", "lunch"]
  evening_wrap:
    enabled: false
  weekly_review:
    enabled: false
  followup_reminder:
    enabled: false
```

The default starts with only morning_briefing + pre_meeting_prep enabled per spec interview step 6 ("stage the rollout").

- [ ] **Step 4: Write `integrations.yaml`**

```yaml
schema_version: 1
integrations:
  google:
    enabled: true
    accounts:
      - email: <YOUR_EMAIL>
        scopes: [gmail, calendar]
  fireflies:
    enabled: false
  web_search:
    enabled: false
```

- [ ] **Step 5: Write `.env.example`**

```bash
# Copy to .env and fill in. Never commit .env.
ANTHROPIC_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
GOOGLE_OAUTH_REFRESH_TOKEN=
```

- [ ] **Step 6: Commit**

```bash
mkdir -p src/cosinabox/templates/user-repo
# (write the files above)
git add src/cosinabox/templates/user-repo
git commit -m "feat(templates): empty user-repo config scaffolds (Plan 1, Task T3.1)"
```

---

### Task T3.2: User-repo Python scaffolding (pyproject, Dockerfile, main.py)

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/templates/user-repo/pyproject.toml`
- Create: `src/cosinabox/templates/user-repo/Dockerfile`
- Create: `src/cosinabox/templates/user-repo/main.py`
- Create: `src/cosinabox/templates/user-repo/.gitignore`

The user repo is a 3-line Python project that depends on `cosinabox` and runs it. The Dockerfile inherits from the cosinabox runtime image (which is built+pushed in Plan 3 — for v0.1 development the `FROM` line points at a local `python:3.11-slim` and is updated in Plan 3 to `cosinabox/runtime:0.1.x`).

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "my-cos"
version = "0.0.1"
requires-python = ">=3.11"
dependencies = [
  "cosinabox[google]>=0.1,<0.2",
]

[tool.hatch.build.targets.wheel]
packages = ["."]
```

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
# Plan 3 will switch this FROM line to cosinabox/runtime:0.1.x.
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml /app/
RUN pip install --no-cache-dir -e .

COPY . /app

CMD ["python", "main.py"]
```

- [ ] **Step 3: Write `main.py`**

```python
"""my-cos entry point. Three lines. Don't touch unless you know why."""

from cosinabox import App

if __name__ == "__main__":
    App().run()
```

- [ ] **Step 4: Write `.gitignore`**

```gitignore
.env
*.db
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.DS_Store
data/
```

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/templates/user-repo/pyproject.toml \
        src/cosinabox/templates/user-repo/Dockerfile \
        src/cosinabox/templates/user-repo/main.py \
        src/cosinabox/templates/user-repo/.gitignore
git commit -m "feat(templates): user-repo python + docker scaffold (Plan 1, Task T3.2)"
```

---

### Task T3.3: User-repo CLAUDE.md (top-level index)

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/templates/user-repo/CLAUDE.md`
- Create: `tests/unit/test_template_claude_md.py`

CLAUDE.md is a **top-level index** that points at the sub-docs in `docs/agent/`. It must be small enough to fit fully into agent context (<200 lines).

- [ ] **Step 1: Write `CLAUDE.md`**

```markdown
# CLAUDE.md — your CoSinaBox

Welcome. This file orients Claude Code (or Cursor / similar) to your personal CoSinaBox repo. It is loaded into the agent's context automatically by the harness.

If you are setting up CoSinaBox for the first time, say to your AI coding agent: **"Set up my CoS."** The agent will read this file, then read `docs/agent/persona-interview.md`, and walk you through the rest.

## What this repo is

This is *your* CoSinaBox. It is a thin wrapper around the `cosinabox` engine (a pip dependency). You configure the engine through 4 files in this directory:

- `personality.md` — your voice and stakes
- `stakeholders.yaml` — your top relationships and how often you want to hear about them
- `jobs.yaml` — which built-in jobs to run, when
- `integrations.yaml` — which tools to load (Google, Fireflies, web search)

Plus `.env` for secrets (never commit).

## How to talk to your AI coding agent about this repo

| If you want to... | Say |
|---|---|
| Set up a brand-new CoS | "Set up my CoS" — agent runs `cosinabox interview` |
| Add a new stakeholder | "Add Sarah Chen, Sequoia, weekly cadence" |
| Change a job schedule | "Move morning briefing to 7am" |
| Adjust personality | "I want briefings to be more skeptical" |
| See what would happen tomorrow | "Simulate tomorrow's morning briefing" |
| Check on health | "Run cosinabox doctor and show me anything that needs attention" |

The agent does the work via `cosinabox` CLI commands documented in `docs/agent/editing-config.md`. You should rarely edit YAML directly.

## Sub-docs (read on demand)

These files are intentionally small so the agent can load each one fully when relevant. The agent's instruction is to read the matching file before acting on a request in that area:

- `docs/agent/safety.md` — non-negotiable rules. **Read first, every session.**
- `docs/agent/persona-interview.md` — the 10-step setup script
- `docs/agent/editing-config.md` — how to edit each config file safely
- `docs/agent/adding-custom-jobs.md` — test-first workflow for the escape hatch
- `docs/agent/oauth-walkthrough.md` — versioned, dated GCP OAuth walkthrough
- `docs/agent/proactive-suggestions.md` — what the agent should watch for and surface

## See also

- `BEST_PRACTICES.md` — the wisdom file. Short. Read it.
- The engine docs: https://github.com/cosinabox/cosinabox (public after Plan 3)

## What's next

If you're a fresh agent session and the user says "set up my CoS", read `docs/agent/persona-interview.md` and start at step 1. Don't improvise — that file is the script.

If the user is an existing user and asks for a specific change, read the matching sub-doc and run the corresponding `cosinabox` CLI command.

If anything is unclear, ask the user before acting. Don't guess on a CoS — generic CoS is the failure mode.
```

- [ ] **Step 2: Write the size test**

`tests/unit/test_template_claude_md.py`:

```python
from __future__ import annotations

from importlib.resources import files


def test_user_repo_claude_md_under_200_lines() -> None:
    text = files("cosinabox.templates.user_repo").joinpath("CLAUDE.md").read_text()
    lines = text.splitlines()
    assert len(lines) < 200, f"CLAUDE.md is {len(lines)} lines, must stay under 200"


def test_user_repo_claude_md_lists_subdocs() -> None:
    text = files("cosinabox.templates.user_repo").joinpath("CLAUDE.md").read_text()
    for sub in ("safety.md", "persona-interview.md", "editing-config.md",
                "adding-custom-jobs.md", "oauth-walkthrough.md",
                "proactive-suggestions.md"):
        assert sub in text
```

- [ ] **Step 3: Make `templates/user_repo` a package**

```bash
touch src/cosinabox/templates/__init__.py
mkdir -p src/cosinabox/templates/user_repo
# Move template files to the user_repo subdir if needed
```

Note the dash-vs-underscore split: the on-disk template directory is `templates/user-repo/` (so users see clean names after `cosinabox init`), but the importable Python package is `templates.user_repo` (because Python doesn't allow dashes). The `cosinabox init` command (T3.13) bridges these by reading from the on-disk path.

For tests that use `importlib.resources`, we need a separate package directory. Easiest: keep `templates/user-repo/` as a data directory, not a package, and have tests read it via filesystem path:

```python
from pathlib import Path
USER_REPO_TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "cosinabox" / "templates" / "user-repo"
```

Update the test accordingly:

```python
from pathlib import Path

USER_REPO_TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "src" / "cosinabox" / "templates" / "user-repo"
)


def test_user_repo_claude_md_under_200_lines() -> None:
    text = (USER_REPO_TEMPLATE / "CLAUDE.md").read_text()
    assert len(text.splitlines()) < 200


def test_user_repo_claude_md_lists_subdocs() -> None:
    text = (USER_REPO_TEMPLATE / "CLAUDE.md").read_text()
    for sub in ("safety.md", "persona-interview.md", "editing-config.md",
                "adding-custom-jobs.md", "oauth-walkthrough.md",
                "proactive-suggestions.md"):
        assert sub in text
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/unit/test_template_claude_md.py -v
git add src/cosinabox/templates/user-repo/CLAUDE.md tests/unit/test_template_claude_md.py
git commit -m "feat(templates): user-repo CLAUDE.md index (Plan 1, Task T3.3)"
```

---

### Task T3.4: docs/agent/safety.md

**Est:** 30 min

**Files:**
- Create: `src/cosinabox/templates/user-repo/docs/agent/safety.md`

The non-negotiable rules. The most important sub-doc.

- [ ] **Step 1: Write `safety.md`**

```markdown
# Safety rules — non-negotiable

These are absolute. No exceptions. Read this file before any other action in this repo.

## API keys

1. **API keys live ONLY in `.env`.** `.env` is in `.gitignore`. Never write a key to a tracked file. Never paste a key into a YAML or markdown file. The pre-commit hook will refuse the commit if it sees a key prefix in a tracked file (`sk-ant-`, `xoxb-`, `AIza`, `ghp_`).

2. **If you accidentally commit a key, rotate it immediately.** The pre-commit hook is a safety net, not a guarantee. After rotating, check the git history with `git log --all -S '<the leaked key>'` and force-rotate any other places it might appear.

## Validation

3. **Always run `cosinabox validate` before committing config edits.** The pre-commit hook does this automatically — never bypass it with `--no-verify`. If validation fails, fix the underlying issue.

4. **Always run `cosinabox simulate <job>` after editing a job's config or prompt.** Dry-run before deploy beats guess-and-pray. The agent should automatically do this; if you (the human) edit a file directly, you must run simulate yourself.

## Engine internals

5. **Never edit files in `.cosinabox/`.** That directory holds engine internals (read-only schema reference copies, the pre-commit hook). Changes there get overwritten by `cosinabox upgrade-docs`.

## Git hygiene

6. **Never `git push --force`.** Never bypass pre-commit hooks with `--no-verify`. Never commit directly to `main`. All changes go through a feature branch + PR + auto-merge.

7. **Deploy via PR merge only.** Never `railway up` or push directly to a Railway-connected branch from your laptop.

## What to do if a rule conflicts with what the user asked

If the user asks you to do something that violates a safety rule (e.g. "just commit my API key, it's a personal repo, doesn't matter"), refuse and explain the rule. The user can override the rule by editing this file — but they must do it explicitly, not by asking you to look the other way.
```

- [ ] **Step 2: Commit**

```bash
mkdir -p src/cosinabox/templates/user-repo/docs/agent
# write file
git add src/cosinabox/templates/user-repo/docs/agent/safety.md
git commit -m "feat(templates): docs/agent/safety.md (Plan 1, Task T3.4)"
```

---

### Task T3.5: docs/agent/persona-interview.md

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/templates/user-repo/docs/agent/persona-interview.md`

The 10-step interview script. The agent invokes `cosinabox interview` (T4.10) which is the engine-owned state machine; this doc explains the flow to the agent and tells it how to relay between user and state machine.

- [ ] **Step 1: Write `persona-interview.md`**

```markdown
# Persona interview — 10-step setup

When the user says "set up my CoS" (or any equivalent), follow this script. **Do not improvise.** The interview is a state machine owned by the engine; you invoke `cosinabox interview` and relay one question at a time to the user, then relay the user's answer back.

## How to run it

```bash
cosinabox interview --start
```

The engine prints the next question. Show the question to the user verbatim. Wait for the user's answer. Then run:

```bash
cosinabox interview --answer "<the user's answer>"
```

Repeat until the engine prints `INTERVIEW COMPLETE`. Each step writes to the appropriate config file automatically.

## The 10 steps

1. **Identity** — name, role, company, timezone. Goes into `personality.md` frontmatter.
2. **Stakes** — *"What's the most important thing happening in your work over the next 6 weeks?"* Becomes the first paragraph of `personality.md` "# Stakes" section. **A CoS without stakes is a chatbot.**
3. **Voice** — *"Pick one: blunt / warm / analytical / formal / playful. Pick a runner-up. What's a phrase a great chief of staff has said to you that you wish you heard more often?"*
4. **Top stakeholders** — *"Name your 5 most important people right now. For each: role, cadence, anything I should know."* Writes to `stakeholders.yaml`. **Start with 5, not 50.**
5. **Calendar reality** — *"Are you back-to-back? What should pre-meeting prep skip (lunch, focus blocks, internal 1:1s)?"* Tunes `pre_meeting_prep.skip_if_calendar_title_matches`.
6. **Job staging** — *"For week 1, I'm enabling only `morning_briefing` and `pre_meeting_prep`. Sound good?"* **Stage the rollout.** Other jobs default to disabled.
7. **API keys + OAuth** — agent walks the user through Telegram BotFather + Anthropic + Google OAuth as a literal step-by-step script from `docs/agent/oauth-walkthrough.md`.
8. **Budget caps** — *"Default daily cap is $15. Want to change?"* **Set caps before going live.**
9. **First simulation** — agent runs `cosinabox simulate morning_briefing --fixture=sample` and shows the output.
10. **Deploy** — agent walks the user through Railway template button + GitHub repo connect + env var entry.

## Pushback

Each step is opinionated. If the user gives an answer that would lead to a bad CoS (e.g. "no stakes, just keep it general"), push back with a one-line explanation of the lesson. Examples:

- "A CoS without stakes is a chatbot. Even a rough sentence helps — what's the biggest thing on your mind right now?"
- "Five stakeholders is a starting point, not a limit. Adding 50 on day one means you'll never read the briefing."

Every opinion is a recommendation, not a block. The user retains override authority.

## After the interview

Run:

```bash
cosinabox validate
cosinabox describe
```

Show the user the English summary of what got configured. Then proceed to step 9 (simulation) and step 10 (deploy).
```

- [ ] **Step 2: Commit**

```bash
git add src/cosinabox/templates/user-repo/docs/agent/persona-interview.md
git commit -m "feat(templates): docs/agent/persona-interview.md (Plan 1, Task T3.5)"
```

---

### Task T3.6: docs/agent/editing-config.md

**Est:** 30 min

**Files:**
- Create: `src/cosinabox/templates/user-repo/docs/agent/editing-config.md`

How to edit each config file safely.

- [ ] **Step 1: Write `editing-config.md`**

```markdown
# Editing config

Prefer **CLI commands over direct edits**. Prefer **config edits over prompt overrides**. Prefer **prompt overrides over custom Python**. In that order.

## Stakeholders

```bash
cosinabox add-stakeholder --name "Sarah Chen" --role "Lead investor (Sequoia)" --cadence weekly --notes "Wants monthly metric updates."
```

When adding a stakeholder, always ask the user for:
- Name (full name preferred)
- Role (one line)
- Cadence (`daily | weekly | biweekly | monthly | quarterly`)
- Notes (optional but encouraged — surface what makes this person useful)

Never leave fields blank. Never invent a cadence; ask.

## Jobs

```bash
cosinabox enable-job morning_briefing
cosinabox set-job-schedule morning_briefing --cron "0 8 * * *"
cosinabox disable-job followup_reminder
```

When enabling a new job, recommend simulate-mode for 2-3 days before relying on it:

```bash
cosinabox simulate <job_name>
```

## Personality

```bash
cosinabox set-persona --role founder
```

This loads the `founder` template. To customize beyond the template, run the persona interview (`docs/agent/persona-interview.md`). Never write a personality from a one-line user request — the result will be generic and the briefings will be too.

## Integrations

Edit `integrations.yaml` directly. Set `enabled: true` for the integrations the user has set up. Never enable an integration without confirming the env var is set in `.env`.

## After any edit

```bash
cosinabox validate
cosinabox describe
```

Show the user the English summary diff. If they're surprised, undo.
```

- [ ] **Step 2: Commit**

```bash
git add src/cosinabox/templates/user-repo/docs/agent/editing-config.md
git commit -m "feat(templates): docs/agent/editing-config.md (Plan 1, Task T3.6)"
```

---

### Task T3.7: docs/agent/adding-custom-jobs.md

**Est:** 30 min

**Files:**
- Create: `src/cosinabox/templates/user-repo/docs/agent/adding-custom-jobs.md`

The escape hatch is risky. Loud doc.

- [ ] **Step 1: Write `adding-custom-jobs.md`**

```markdown
# Adding custom jobs

**Custom jobs are a last resort.** 90% of "I want a custom thing" is "I want to override a prompt." Try these in order:

1. **Edit `personality.md`** — for behavior changes.
2. **Drop a `prompts/<job_name>.md` file** — for tone or format overrides on built-in jobs.
3. **Tweak `jobs.yaml`** — for schedule, filter, or threshold changes.
4. **Custom job in `custom_jobs/<name>.py`** — only if none of the above work.

## Test-first

If you do need a custom job, **write the test before the job**.

```bash
mkdir -p custom_jobs tests
```

Example structure:

```python
# tests/test_my_custom_job.py
from __future__ import annotations

from custom_jobs.my_custom_job import MyCustomJob


def test_my_custom_job_returns_string():
    job = MyCustomJob()
    result = job.run(stakeholders=[])
    assert isinstance(result, str)
```

```python
# custom_jobs/my_custom_job.py
from __future__ import annotations

from cosinabox.jobs.base import Job, JobContext


class MyCustomJob(Job):
    name = "my_custom_job"

    def run(self, context: JobContext) -> str:
        return "Hello from my custom job."
```

Run:

```bash
cosinabox test
cosinabox simulate my_custom_job
```

## Auto-discovery

Custom jobs in `custom_jobs/*.py` are auto-discovered at startup. The class must extend `cosinabox.jobs.base.Job` and have a unique `name` attribute. If you add a custom job and it doesn't appear, run `cosinabox describe` and look for it in the "loaded custom jobs" section.

## Risk

Custom jobs run **dynamic Python you wrote**. There is no sandbox. Don't paste code from the internet without reading it. Don't import secrets in custom jobs (use env vars). Single-user self-hosted only — never share custom jobs with strangers.

## After deploying a custom job

```bash
cosinabox doctor --json
```

Look for unexpected entries. If your custom job blew the cost cap, the doctor will surface `cost_runaway`.
```

- [ ] **Step 2: Commit**

```bash
git add src/cosinabox/templates/user-repo/docs/agent/adding-custom-jobs.md
git commit -m "feat(templates): docs/agent/adding-custom-jobs.md (Plan 1, Task T3.7)"
```

---

### Task T3.8: docs/agent/oauth-walkthrough.md (versioned + dated)

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/templates/user-repo/docs/agent/oauth-walkthrough.md`

Versioned doc. The header line is **"Last validated against Google Cloud console UI on YYYY-MM-DD"**. When the GCP UI changes, this doc is updated and re-shipped via `cosinabox upgrade-docs` (T4.8).

- [ ] **Step 1: Write `oauth-walkthrough.md`**

```markdown
# Google OAuth walkthrough

> **Last validated against Google Cloud console UI on 2026-04-12.**
> If steps are stale, run `cosinabox upgrade-docs` to refresh, or report at https://github.com/cosinabox/cosinabox/issues.

This script walks the user through getting a Google OAuth refresh token for Gmail + Calendar. The agent reads each step *one at a time* and waits for the user's confirmation before moving to the next.

## Why this is manual

Google OAuth requires manual clicks in the GCP console. There is no API to automate this for the consumer flow. Plan ~15 minutes.

## Prerequisites

- A Google account (the one whose Gmail + Calendar your CoS will read)
- A web browser
- A terminal with `cosinabox` installed

## Steps

1. **Open the GCP console.** Go to https://console.cloud.google.com/. Sign in with the account whose Gmail + Calendar you want CoSinaBox to access.

2. **Create a project (or use an existing one).** Click the project picker in the top bar → "New Project". Name it `my-cos` (or anything). Click "Create". Wait for the notification that the project is ready, then select it.

3. **Enable the Gmail API.** Go to https://console.cloud.google.com/apis/library/gmail.googleapis.com → click "Enable". Wait ~30 seconds.

4. **Enable the Calendar API.** Go to https://console.cloud.google.com/apis/library/calendar-json.googleapis.com → click "Enable".

5. **Configure the OAuth consent screen.** Go to APIs & Services → OAuth consent screen.
   - User Type: **External**. Click "Create".
   - App name: `my-cos`
   - User support email: your email
   - Developer contact: your email
   - Click "Save and continue" through the next pages without changing anything.
   - On "Test users", add your own email. Click "Save and continue".

6. **Create OAuth credentials.** Go to APIs & Services → Credentials → Create Credentials → OAuth client ID.
   - Application type: **Desktop app**
   - Name: `my-cos`
   - Click "Create".
   - Copy the **Client ID** and **Client Secret** that pop up.

7. **Set the env vars in `.env` (locally).**

   ```bash
   echo "GOOGLE_OAUTH_CLIENT_ID=<paste client id>" >> .env
   echo "GOOGLE_OAUTH_CLIENT_SECRET=<paste client secret>" >> .env
   ```

8. **Run the cosinabox auth flow.**

   ```bash
   cosinabox auth google
   ```

   This opens a browser tab to Google's OAuth consent screen. Sign in with the same account you used in step 1. Approve the requested scopes (gmail.modify, calendar). The browser will redirect to a localhost URL — that's expected. The terminal will print:

   ```
   GOOGLE_OAUTH_REFRESH_TOKEN=1//0gXXXXXX...
   ```

9. **Save the refresh token to `.env`.**

   ```bash
   echo "GOOGLE_OAUTH_REFRESH_TOKEN=1//0gXXXXXX..." >> .env
   ```

10. **Verify it works.**

    ```bash
    cosinabox doctor
    ```

    Look for `oauth_expiring`: should be green (refresh token is fresh).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Access blocked: This app's request is invalid" | Consent screen not configured | Re-do step 5 |
| "Error 403: access_denied" | Test user not added | Add your email under step 5 "Test users" |
| `cosinabox auth google` hangs | Firewall blocks localhost callback | Run from a machine where localhost:8080 is reachable |
| `oauth_expiring` flagged red | Token already stale | Re-run `cosinabox auth google` |
```

- [ ] **Step 2: Commit**

```bash
git add src/cosinabox/templates/user-repo/docs/agent/oauth-walkthrough.md
git commit -m "feat(templates): docs/agent/oauth-walkthrough.md, dated 2026-04-12 (Plan 1, Task T3.8)"
```

---

### Task T3.9: docs/agent/proactive-suggestions.md

**Est:** 30 min

**Files:**
- Create: `src/cosinabox/templates/user-repo/docs/agent/proactive-suggestions.md`

What the agent should watch for and surface without being asked.

- [ ] **Step 1: Write `proactive-suggestions.md`**

```markdown
# Proactive suggestions

These aren't rules — they're patterns the agent should notice and surface to the user without being asked. Good agents are proactive but not noisy. The threshold for surfacing should be: *"Would the user thank me for noticing?"*

## After 2 weeks of usage

- If `followup_reminder` is still disabled and `stakeholders.yaml` has 5+ entries with stale `last_contact` dates, suggest enabling it.
- If `weekly_review` is disabled, suggest enabling it for next Friday.

## When the user mentions a missed meeting

- Check whether `pre_meeting_prep` is enabled in `jobs.yaml`. If not, suggest enabling it.
- If it's enabled but didn't fire for the meeting in question, run `cosinabox doctor` and surface `prep_noise` (filter overly aggressive) or `oauth_expiring` (auth token broken).

## When the user complains the briefing is wrong

- Recommend a **prompt override** (`prompts/morning_briefing.md`) over editing `personality.md` — overrides are more surgical and less likely to break other jobs.
- If the issue is "wrong stakeholder context", recommend updating `stakeholders.yaml` instead.
- If the issue is "wrong tone", recommend the persona interview to revise voice.

## When `cosinabox doctor` flags something

- Surface the flag immediately. Don't wait until the next session.
- If `cost_runaway` fires: surface the daily spend, suggest a tighter cap, suggest tightening prompts.
- If `secret_in_tracked_file` fires: STOP. This is a security incident. Walk the user through key rotation immediately.
- If `oauth_expiring` fires: walk the user through `cosinabox auth google` again.

## When the user adds a stakeholder

- Confirm cadence is realistic, not aspirational. "Can you actually contact this person weekly?" If no, suggest monthly.

## When the user asks for a custom job

- Push back. 90% of the time the answer is a prompt override. Read `docs/agent/adding-custom-jobs.md` to the user before writing Python.

## What NOT to surface proactively

- Cost numbers below the cap. (Daily spend is interesting only if it's hot.)
- Routine job successes. ("Morning briefing fired at 8:00am" is not a notification.)
- Doctor flags that resolve themselves.

Be helpful. Don't be a pager.
```

- [ ] **Step 2: Commit**

```bash
git add src/cosinabox/templates/user-repo/docs/agent/proactive-suggestions.md
git commit -m "feat(templates): docs/agent/proactive-suggestions.md (Plan 1, Task T3.9)"
```

---

### Task T3.10: BEST_PRACTICES.md

**Est:** 30 min

**Files:**
- Create: `src/cosinabox/templates/user-repo/BEST_PRACTICES.md`

The wisdom file. Short.

- [ ] **Step 1: Write `BEST_PRACTICES.md`**

```markdown
# Best practices

The "wisdom file." Short, opinionated, written for humans (and read by agents).

## Start small

Two jobs, five stakeholders. Add more after a week of dogfooding. The CoS only works if you actually read the briefing.

## Tune after, not before

Don't try to perfect `personality.md` on day one. Run for a week. Let the briefings show you what's wrong. Then revise.

## The morning briefing is a contract

If you stop reading the briefing, the bot has failed. Either the content is wrong (revise) or the timing is wrong (re-schedule). Don't let it fade.

## Stakeholder cadence is honest, not aspirational

If you can't actually contact someone weekly, set monthly. Otherwise the follow-up reminder turns into noise and you'll mute it.

## Custom jobs are a last resort

90% of "I want a custom thing" is "I want to override a prompt." Try a prompt override first (`prompts/<job_name>.md`).

## Cost caps are a forcing function, not a budget

Hitting the cap means your prompts are too greedy. Don't raise the cap — tighten the prompts.

## Trust the doctor

When `cosinabox doctor` flags something, fix it that week. Doctor flags compound; ignored flags become outages.

## Don't fork the engine

If you find yourself wanting to fork `cosinabox`, open an issue first. Forks fragment the community and the maintainer can't help you. Custom jobs are the right escape hatch for ~99% of cases.
```

- [ ] **Step 2: Commit**

```bash
git add src/cosinabox/templates/user-repo/BEST_PRACTICES.md
git commit -m "feat(templates): BEST_PRACTICES.md (Plan 1, Task T3.10)"
```

---

### Task T3.11: Pre-commit hook script for the user repo

**Est:** 2 hr

**Files:**
- Create: `src/cosinabox/templates/user-repo/.cosinabox/pre-commit`
- Create: `src/cosinabox/templates/user-repo/.cosinabox/install-hook.sh`
- Create: `tests/integration/test_user_repo_pre_commit.py`

Two pieces:
1. `.cosinabox/pre-commit` — the hook script. Runs `cosinabox validate` and a secret scan against staged files.
2. `.cosinabox/install-hook.sh` — installs the hook into `.git/hooks/pre-commit` (called by `cosinabox init`).

- [ ] **Step 1: Write the hook script**

`src/cosinabox/templates/user-repo/.cosinabox/pre-commit`:

```bash
#!/bin/bash
set -e

# cosinabox user-repo pre-commit hook.
# 1. Validate config
# 2. Scan staged files for known secret prefixes

# 1. Validate
if ! cosinabox validate; then
  echo "::error::cosinabox validate failed. Fix config errors before committing."
  echo "::error::Run \`cosinabox validate\` to see details."
  exit 1
fi

# 2. Secret scan on staged files
SECRET_PREFIXES='(sk-ant-|xoxb-|xoxp-|AIza[0-9A-Za-z_-]{35}|ghp_[A-Za-z0-9]{36}|github_pat_)'
LEAK_FOUND=0
while IFS= read -r -d '' file; do
  if grep -lE "$SECRET_PREFIXES" "$file" >/dev/null 2>&1; then
    echo "::error::Possible secret detected in $file"
    LEAK_FOUND=1
  fi
done < <(git diff --cached --name-only -z)

if [ "$LEAK_FOUND" -ne 0 ]; then
  echo "::error::Secret scan failed. Move secrets to .env and re-stage."
  exit 1
fi

exit 0
```

- [ ] **Step 2: Write the install script**

`src/cosinabox/templates/user-repo/.cosinabox/install-hook.sh`:

```bash
#!/bin/bash
set -e
HOOK_DIR=$(git rev-parse --git-path hooks)
SOURCE=".cosinabox/pre-commit"
TARGET="$HOOK_DIR/pre-commit"
if [ ! -f "$SOURCE" ]; then
  echo "::error::$SOURCE not found. Run from your user repo root."
  exit 1
fi
ln -sf "$(pwd)/$SOURCE" "$TARGET"
chmod +x "$SOURCE"
echo "::notice::Installed cosinabox pre-commit hook at $TARGET"
```

- [ ] **Step 3: Write the integration test**

`tests/integration/test_user_repo_pre_commit.py`:

```python
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "cosinabox" / "templates" / "user-repo"


@pytest.fixture
def fresh_user_repo(tmp_path: Path) -> Path:
    import shutil

    dest = tmp_path / "cos"
    shutil.copytree(TEMPLATE, dest)
    subprocess.run(["git", "init"], cwd=dest, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=dest, check=True, capture_output=True)
    return dest


def test_secret_scan_blocks_anthropic_key(fresh_user_repo: Path) -> None:
    leaky = fresh_user_repo / "personality.md"
    leaky.write_text(leaky.read_text() + "\n\nDEBUG: sk-ant-12345\n")
    subprocess.run(["git", "add", "personality.md"], cwd=fresh_user_repo, check=True)
    result = subprocess.run(
        ["bash", str(fresh_user_repo / ".cosinabox" / "pre-commit")],
        cwd=fresh_user_repo,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": os.environ.get("PATH", "")},
    )
    assert result.returncode != 0
    assert "secret" in (result.stdout + result.stderr).lower()
```

- [ ] **Step 4: Run + commit**

```bash
chmod +x src/cosinabox/templates/user-repo/.cosinabox/pre-commit \
        src/cosinabox/templates/user-repo/.cosinabox/install-hook.sh
pytest tests/integration/test_user_repo_pre_commit.py -v
git add src/cosinabox/templates/user-repo/.cosinabox tests/integration/test_user_repo_pre_commit.py
git commit -m "feat(templates): pre-commit hook with validate + secret scan (Plan 1, Task T3.11)"
```

---

### Task T3.12: `.cosinabox/schemas/` read-only schema reference copies

**Est:** 30 min

**Files:**
- Create: `src/cosinabox/templates/user-repo/.cosinabox/schemas/personality.schema.json` (copy)
- Create: `src/cosinabox/templates/user-repo/.cosinabox/schemas/stakeholders.schema.json` (copy)
- Create: `src/cosinabox/templates/user-repo/.cosinabox/schemas/jobs.schema.json` (copy)
- Create: `src/cosinabox/templates/user-repo/.cosinabox/schemas/integrations.schema.json` (copy)
- Create: `src/cosinabox/templates/user-repo/.cosinabox/README.md`

These are read-only reference copies for IDE autocompletion. Live validation always uses the schemas from the installed engine (per spec section 4: "Used by `cosinabox validate` (always loaded from the installed engine, not from disk copies in the user repo)").

- [ ] **Step 1: Write a copy script and the README**

`src/cosinabox/templates/user-repo/.cosinabox/README.md`:

```markdown
# .cosinabox/

Engine internals. **Do not edit.**

- `pre-commit` — git hook installed by `cosinabox init`. Runs `cosinabox validate` + secret scan.
- `install-hook.sh` — bootstrap script that links the pre-commit hook into `.git/hooks/`.
- `schemas/` — read-only reference copies of the JSON Schemas. Live validation always uses the schemas from the installed `cosinabox` engine, not from this directory.

To refresh this directory after upgrading the engine, run `cosinabox upgrade-docs`.
```

- [ ] **Step 2: Add a build step that copies schemas at install time**

Since the user-repo template is shipped inside the cosinabox wheel, the schemas in `.cosinabox/schemas/` need to be copied from `src/cosinabox/schemas/` at template-build time. Easiest: add a `Makefile` target in the cosinabox repo that runs before tests:

`Makefile` (root):

```makefile
.PHONY: sync-template-schemas
sync-template-schemas:
	mkdir -p src/cosinabox/templates/user-repo/.cosinabox/schemas
	cp src/cosinabox/schemas/*.schema.json src/cosinabox/templates/user-repo/.cosinabox/schemas/

test: sync-template-schemas
	pytest -q
```

Or simpler for v0.1: just copy them by hand during this task and call it out in the milestone retro:

```bash
mkdir -p src/cosinabox/templates/user-repo/.cosinabox/schemas
cp src/cosinabox/schemas/*.schema.json src/cosinabox/templates/user-repo/.cosinabox/schemas/
```

- [ ] **Step 3: Commit**

```bash
git add src/cosinabox/templates/user-repo/.cosinabox/schemas \
        src/cosinabox/templates/user-repo/.cosinabox/README.md \
        Makefile
git commit -m "feat(templates): .cosinabox/schemas/ reference copies (Plan 1, Task T3.12)"
```

---

### Task T3.13: `cosinabox init <dir>` command

**Est:** 2 hr

**Files:**
- Create: `src/cosinabox/cli/init.py`
- Modify: `src/cosinabox/cli/main.py` (register `init`)
- Create: `tests/integration/test_cli_init.py`

`cosinabox init my-cos` creates a directory and copies the user-repo template into it. Errors loudly if the target directory exists and is non-empty. Prints the "open in Claude Code" message at the end.

- [ ] **Step 1: Write the failing test**

`tests/integration/test_cli_init.py`:

```python
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli


def test_init_creates_user_repo(tmp_path: Path) -> None:
    target = tmp_path / "my-cos"
    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(target)])
    assert result.exit_code == 0, result.output
    assert (target / "personality.md").exists()
    assert (target / "stakeholders.yaml").exists()
    assert (target / "jobs.yaml").exists()
    assert (target / "integrations.yaml").exists()
    assert (target / "main.py").exists()
    assert (target / "CLAUDE.md").exists()
    assert (target / "docs" / "agent" / "safety.md").exists()
    assert (target / ".cosinabox" / "pre-commit").exists()
    assert "Open this directory in Claude Code" in result.output


def test_init_refuses_non_empty_dir(tmp_path: Path) -> None:
    target = tmp_path / "my-cos"
    target.mkdir()
    (target / "junk.txt").write_text("hi")
    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(target)])
    assert result.exit_code != 0
    assert "not empty" in result.output.lower()
```

- [ ] **Step 2: Implement `src/cosinabox/cli/init.py`**

```python
"""`cosinabox init <dir>` — scaffold a new user repo."""

from __future__ import annotations

import shutil
from pathlib import Path

import click

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1] / "templates" / "user-repo"
)


@click.command("init")
@click.argument("dest", type=click.Path(file_okay=False, path_type=Path))
def init_cmd(dest: Path) -> None:
    """Scaffold a new user repo at <dest>."""
    if dest.exists() and any(dest.iterdir()):
        raise click.ClickException(f"{dest} exists and is not empty.")
    shutil.copytree(TEMPLATE_ROOT, dest)
    # Make hook executable (copytree drops permissions on some systems).
    hook = dest / ".cosinabox" / "pre-commit"
    if hook.exists():
        hook.chmod(0o755)
    install = dest / ".cosinabox" / "install-hook.sh"
    if install.exists():
        install.chmod(0o755)
    click.echo(f"Your CoSinaBox skeleton is ready in {dest}.")
    click.echo("Open this directory in Claude Code (or Cursor) and say 'set up my CoS.'")
    click.echo("Claude Code will read CLAUDE.md and walk you through the rest.")
```

Register in `cli/main.py`:

```python
from cosinabox.cli.init import init_cmd
cli.add_command(init_cmd)
```

- [ ] **Step 3: Update pyproject.toml to ship the template**

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/cosinabox"]

[tool.hatch.build.targets.wheel.force-include]
"src/cosinabox/personas/founder.md" = "cosinabox/personas/founder.md"
"src/cosinabox/schemas/personality.schema.json" = "cosinabox/schemas/personality.schema.json"
"src/cosinabox/schemas/stakeholders.schema.json" = "cosinabox/schemas/stakeholders.schema.json"
"src/cosinabox/schemas/jobs.schema.json" = "cosinabox/schemas/jobs.schema.json"
"src/cosinabox/schemas/integrations.schema.json" = "cosinabox/schemas/integrations.schema.json"
"src/cosinabox/templates/user-repo" = "cosinabox/templates/user-repo"
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/integration/test_cli_init.py -v
ruff check src/cosinabox/cli/init.py tests/integration/test_cli_init.py
mypy src/cosinabox/cli
git add src/cosinabox/cli/init.py src/cosinabox/cli/main.py pyproject.toml tests/integration/test_cli_init.py
git commit -m "feat(cli): cosinabox init <dir> (Plan 1, Task T3.13)"
```

---

### Task T3.14: M3 verification + PR

**Est:** 30 min

- [ ] **Step 1: End-to-end smoke test**

```bash
rm -rf /tmp/test-cos
cosinabox init /tmp/test-cos
cosinabox -C /tmp/test-cos validate
ls /tmp/test-cos/docs/agent/
```

Expected: init prints the welcome message, validate passes, all 6 sub-docs exist.

- [ ] **Step 2: Run the full M3 test suite**

```bash
ruff check src tests
ruff format --check src tests
mypy src/cosinabox
pytest -q
```

- [ ] **Step 3: Push, PR, auto-merge**

```bash
git push
gh pr create --title "Plan 1 Milestone 3: user repo template + agent docs" --body "$(cat <<'EOF'
## Summary
Adds the user-repo template, all 6 docs/agent/* files, BEST_PRACTICES.md, the pre-commit hook with secret scanning, and the `cosinabox init` command. After this milestone, a fresh user can run one command and get a complete agent-ready repo.

## Test plan
- [ ] `cosinabox init /tmp/test-cos` succeeds
- [ ] `cosinabox -C /tmp/test-cos validate` returns exit 0
- [ ] All 6 docs/agent/*.md files copied
- [ ] Pre-commit hook blocks a fake leaked key
EOF
)"
gh pr merge --auto --squash --delete-branch
```

- [ ] **Step 4: Write M3 retro within 24 hours of merge**

Same as previous milestones.

---

## Milestone 4 — CLI commands + interview state machine + doctor checks

**Goal:** All CLI commands the spec lists exist and are exercised by tests. The interview state machine works end-to-end against a scripted set of answers. All 10 doctor checks fire on the right inputs and return parseable JSON.

**Done when:**
- Every command in spec Section 5 "CLI commands" has an implementation, a unit test, and `--json` output where applicable.
- `cosinabox interview --start` + `cosinabox interview --answer "..."` walks the 10 steps end-to-end against a test fixture and produces a fully-populated user repo.
- `cosinabox doctor --json` runs all 10 checks and returns a list of `{check, status, message}` items.
- `cosinabox describe` prints an English summary of any user repo.
- `cosinabox migrate` walks `schema_version` forward (or no-ops if already current).

**PR title:** `Plan 1 Milestone 4: CLI + interview + doctor`
**PR exit criteria:** All M4 tasks checked; full smoke test (`cosinabox init` → `cosinabox interview` end-to-end → `cosinabox simulate` → `cosinabox doctor`) passes against the sample fixture; CI green.

---

### Task T4.1: `cosinabox describe` command

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/cli/describe.py`
- Modify: `src/cosinabox/cli/main.py`
- Create: `tests/unit/test_cli_describe.py`

`describe` reads the 4 user config files and prints a 10-15 line English summary: who you are, your stakes, your top stakeholders by cadence, your enabled jobs and schedules, your enabled integrations.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_cli_describe.py`:

```python
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample-user-repo"


def test_describe_outputs_english_summary() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "describe"])
    assert result.exit_code == 0
    assert "Alex" in result.output
    assert "morning_briefing" in result.output
    assert "Sarah Chen" in result.output


def test_describe_json_mode() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "describe", "--json"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.output)
    assert "name" in data
    assert "jobs" in data
```

- [ ] **Step 2: Implement `src/cosinabox/cli/describe.py`**

```python
"""`cosinabox describe` — English summary of the configured CoS."""

from __future__ import annotations

import json as jsonlib
import re
from pathlib import Path

import click
import yaml

_FRONT = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def _load(config_dir: Path) -> dict:
    out: dict = {}
    p = config_dir / "personality.md"
    if p.exists():
        text = p.read_text()
        m = _FRONT.match(text)
        if m:
            out.update(yaml.safe_load(m.group(1)))
    for fname, key in (
        ("stakeholders.yaml", "stakeholders"),
        ("jobs.yaml", "jobs"),
        ("integrations.yaml", "integrations"),
    ):
        f = config_dir / fname
        if f.exists():
            data = yaml.safe_load(f.read_text())
            out[key] = data.get(key)
    return out


@click.command("describe")
@click.option("--json", "json_out", is_flag=True)
@click.pass_context
def describe_cmd(ctx: click.Context, json_out: bool) -> None:
    """English summary of the configured CoS."""
    config_dir: Path = ctx.obj["config_dir"]
    data = _load(config_dir)
    if json_out:
        click.echo(jsonlib.dumps(data, indent=2, default=str))
        return
    click.echo(f"CoSinaBox for {data.get('name', '<no name>')} ({data.get('role', '')})")
    click.echo(f"Timezone: {data.get('timezone', '?')}")
    click.echo("")
    stakeholders = data.get("stakeholders") or []
    click.echo(f"Stakeholders ({len(stakeholders)}):")
    for s in stakeholders[:10]:
        click.echo(f"  - {s.get('name')} ({s.get('cadence')})")
    click.echo("")
    jobs = data.get("jobs") or {}
    enabled = [n for n, j in jobs.items() if j.get("enabled")]
    click.echo(f"Enabled jobs ({len(enabled)}):")
    for n in enabled:
        click.echo(f"  - {n} ({jobs[n].get('schedule', 'no schedule')})")
    click.echo("")
    integrations = data.get("integrations") or {}
    enabled_int = [n for n, i in integrations.items() if i.get("enabled")]
    click.echo(f"Integrations: {', '.join(enabled_int) or '(none)'}")
```

Register in `cli/main.py`:

```python
from cosinabox.cli.describe import describe_cmd
cli.add_command(describe_cmd)
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_cli_describe.py -v
ruff check src/cosinabox/cli tests/unit/test_cli_describe.py
mypy src/cosinabox/cli
git add src/cosinabox/cli/describe.py src/cosinabox/cli/main.py tests/unit/test_cli_describe.py
git commit -m "feat(cli): cosinabox describe (Plan 1, Task T4.1)"
```

---

### Task T4.2: `cosinabox add-stakeholder` command

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/cli/add_stakeholder.py`
- Modify: `src/cosinabox/cli/main.py`
- Create: `tests/unit/test_cli_add_stakeholder.py`

Appends a new entry to `stakeholders.yaml`. Validates against the schema before writing. Refuses to add a duplicate name.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_cli_add_stakeholder.py`:

```python
from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from cosinabox.cli.main import cli


def _seed(tmp: Path) -> None:
    (tmp / "stakeholders.yaml").write_text(
        "schema_version: 1\nstakeholders:\n  - name: Existing\n    cadence: weekly\n"
    )


def test_add_stakeholder_appends(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["-C", str(tmp_path), "add-stakeholder",
         "--name", "Sarah Chen",
         "--role", "Lead investor",
         "--cadence", "weekly",
         "--notes", "Replies in mornings."],
    )
    assert result.exit_code == 0
    data = yaml.safe_load((tmp_path / "stakeholders.yaml").read_text())
    names = [s["name"] for s in data["stakeholders"]]
    assert "Sarah Chen" in names


def test_add_stakeholder_rejects_duplicate(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["-C", str(tmp_path), "add-stakeholder",
         "--name", "Existing", "--cadence", "weekly"],
    )
    assert result.exit_code != 0
    assert "already exists" in result.output.lower()


def test_add_stakeholder_rejects_bad_cadence(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["-C", str(tmp_path), "add-stakeholder",
         "--name", "X", "--cadence", "yearly"],
    )
    assert result.exit_code != 0
```

- [ ] **Step 2: Implement `src/cosinabox/cli/add_stakeholder.py`**

```python
"""`cosinabox add-stakeholder`."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import click
import yaml
from jsonschema import ValidationError, validate

from cosinabox.schemas import load_schema

VALID_CADENCES = ("daily", "weekly", "biweekly", "monthly", "quarterly")


@click.command("add-stakeholder")
@click.option("--name", required=True)
@click.option("--role", default="")
@click.option(
    "--cadence",
    required=True,
    type=click.Choice(VALID_CADENCES),
)
@click.option("--last-contact", default=None, help="ISO date; defaults to today.")
@click.option("--notes", default="")
@click.pass_context
def add_stakeholder_cmd(
    ctx: click.Context,
    name: str,
    role: str,
    cadence: str,
    last_contact: str | None,
    notes: str,
) -> None:
    """Append a stakeholder to stakeholders.yaml."""
    config_dir: Path = ctx.obj["config_dir"]
    path = config_dir / "stakeholders.yaml"
    data = yaml.safe_load(path.read_text()) if path.exists() else {
        "schema_version": 1, "stakeholders": []
    }
    existing = {s["name"] for s in data.get("stakeholders", [])}
    if name in existing:
        raise click.ClickException(f"{name} already exists in stakeholders.yaml")
    entry = {
        "name": name,
        "role": role,
        "cadence": cadence,
        "last_contact": last_contact or date.today().isoformat(),
        "notes": notes,
    }
    data.setdefault("stakeholders", []).append(entry)
    try:
        validate(instance=data, schema=load_schema("stakeholders"))
    except ValidationError as e:
        raise click.ClickException(f"Schema validation failed: {e.message}")
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    click.echo(f"Added {name} ({cadence})")
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_cli_add_stakeholder.py -v
git add src/cosinabox/cli/add_stakeholder.py src/cosinabox/cli/main.py tests/unit/test_cli_add_stakeholder.py
git commit -m "feat(cli): cosinabox add-stakeholder (Plan 1, Task T4.2)"
```

(Don't forget to register `add_stakeholder_cmd` in `cli/main.py`.)

---

### Task T4.3: `cosinabox set-job-schedule` command

**Est:** 30 min

**Files:**
- Create: `src/cosinabox/cli/set_job_schedule.py`
- Modify: `src/cosinabox/cli/main.py`
- Create: `tests/unit/test_cli_set_job_schedule.py`

Updates a job's `schedule` field in `jobs.yaml` after validating the cron string.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_cli_set_job_schedule.py`:

```python
from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from cosinabox.cli.main import cli


def _seed(tmp: Path) -> None:
    (tmp / "jobs.yaml").write_text(
        'schema_version: 1\njobs:\n  morning_briefing:\n    enabled: true\n    schedule: "0 8 * * *"\n'
    )


def test_set_schedule_updates_field(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["-C", str(tmp_path), "set-job-schedule",
              "morning_briefing", "--cron", "0 7 * * *"],
    )
    assert result.exit_code == 0
    data = yaml.safe_load((tmp_path / "jobs.yaml").read_text())
    assert data["jobs"]["morning_briefing"]["schedule"] == "0 7 * * *"


def test_set_schedule_rejects_unknown_job(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["-C", str(tmp_path), "set-job-schedule", "no_such", "--cron", "0 7 * * *"],
    )
    assert result.exit_code != 0


def test_set_schedule_rejects_bad_cron(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["-C", str(tmp_path), "set-job-schedule",
              "morning_briefing", "--cron", "not a cron"],
    )
    assert result.exit_code != 0
```

- [ ] **Step 2: Implement `src/cosinabox/cli/set_job_schedule.py`**

```python
"""`cosinabox set-job-schedule <job> --cron <cron>`."""

from __future__ import annotations

from pathlib import Path

import click
import yaml
from apscheduler.triggers.cron import CronTrigger


@click.command("set-job-schedule")
@click.argument("job_name")
@click.option("--cron", required=True)
@click.pass_context
def set_job_schedule_cmd(ctx: click.Context, job_name: str, cron: str) -> None:
    """Update a job's cron schedule."""
    config_dir: Path = ctx.obj["config_dir"]
    path = config_dir / "jobs.yaml"
    data = yaml.safe_load(path.read_text())
    if job_name not in data.get("jobs", {}):
        raise click.ClickException(f"Unknown job: {job_name}")
    try:
        CronTrigger.from_crontab(cron)
    except Exception as e:
        raise click.ClickException(f"Invalid cron expression: {e}")
    data["jobs"][job_name]["schedule"] = cron
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    click.echo(f"Updated {job_name} schedule to {cron}")
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_cli_set_job_schedule.py -v
git add src/cosinabox/cli/set_job_schedule.py src/cosinabox/cli/main.py tests/unit/test_cli_set_job_schedule.py
git commit -m "feat(cli): cosinabox set-job-schedule (Plan 1, Task T4.3)"
```

---

### Task T4.4: `cosinabox enable-job` / `disable-job` commands

**Est:** 30 min

**Files:**
- Create: `src/cosinabox/cli/enable_job.py`
- Create: `src/cosinabox/cli/disable_job.py`
- Modify: `src/cosinabox/cli/main.py`
- Create: `tests/unit/test_cli_enable_disable_job.py`

Two commands sharing the same logic with a `True`/`False` flag. They flip `jobs.<name>.enabled` in `jobs.yaml`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_cli_enable_disable_job.py`:

```python
from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from cosinabox.cli.main import cli


def _seed(tmp: Path) -> None:
    (tmp / "jobs.yaml").write_text(
        'schema_version: 1\njobs:\n  morning_briefing:\n    enabled: false\n    schedule: "0 8 * * *"\n'
    )


def test_enable_job_flips_flag(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "enable-job", "morning_briefing"])
    assert result.exit_code == 0
    data = yaml.safe_load((tmp_path / "jobs.yaml").read_text())
    assert data["jobs"]["morning_briefing"]["enabled"] is True


def test_disable_job_flips_flag(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / "jobs.yaml").write_text(
        'schema_version: 1\njobs:\n  morning_briefing:\n    enabled: true\n'
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "disable-job", "morning_briefing"])
    assert result.exit_code == 0
    data = yaml.safe_load((tmp_path / "jobs.yaml").read_text())
    assert data["jobs"]["morning_briefing"]["enabled"] is False
```

- [ ] **Step 2: Implement both commands**

`src/cosinabox/cli/enable_job.py`:

```python
"""`cosinabox enable-job <name>`."""

from __future__ import annotations

from pathlib import Path

import click
import yaml


def _flip(config_dir: Path, job_name: str, value: bool) -> None:
    path = config_dir / "jobs.yaml"
    data = yaml.safe_load(path.read_text())
    if job_name not in data.get("jobs", {}):
        raise click.ClickException(f"Unknown job: {job_name}")
    data["jobs"][job_name]["enabled"] = value
    path.write_text(yaml.safe_dump(data, sort_keys=False))


@click.command("enable-job")
@click.argument("job_name")
@click.pass_context
def enable_job_cmd(ctx: click.Context, job_name: str) -> None:
    _flip(ctx.obj["config_dir"], job_name, True)
    click.echo(f"Enabled {job_name}")
```

`src/cosinabox/cli/disable_job.py`:

```python
"""`cosinabox disable-job <name>`."""

from __future__ import annotations

import click

from cosinabox.cli.enable_job import _flip


@click.command("disable-job")
@click.argument("job_name")
@click.pass_context
def disable_job_cmd(ctx: click.Context, job_name: str) -> None:
    _flip(ctx.obj["config_dir"], job_name, False)
    click.echo(f"Disabled {job_name}")
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_cli_enable_disable_job.py -v
git add src/cosinabox/cli/enable_job.py src/cosinabox/cli/disable_job.py src/cosinabox/cli/main.py tests/unit/test_cli_enable_disable_job.py
git commit -m "feat(cli): enable-job + disable-job (Plan 1, Task T4.4)"
```

---

### Task T4.5: `cosinabox set-persona` command

**Est:** 30 min

**Files:**
- Create: `src/cosinabox/cli/set_persona.py`
- Modify: `src/cosinabox/cli/main.py`
- Create: `tests/unit/test_cli_set_persona.py`

Loads a persona template (only `founder` exists in v0.1) and copies it to `personality.md` in the user repo. Refuses to overwrite an existing file unless `--force` is passed.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_cli_set_persona.py`:

```python
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli


def test_set_persona_creates_file(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "set-persona", "--role", "founder"])
    assert result.exit_code == 0
    text = (tmp_path / "personality.md").read_text()
    assert "schema_version: 1" in text
    assert "# Voice" in text


def test_set_persona_refuses_overwrite_without_force(tmp_path: Path) -> None:
    (tmp_path / "personality.md").write_text("existing content")
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "set-persona", "--role", "founder"])
    assert result.exit_code != 0


def test_set_persona_force_overwrites(tmp_path: Path) -> None:
    (tmp_path / "personality.md").write_text("existing content")
    runner = CliRunner()
    result = runner.invoke(
        cli, ["-C", str(tmp_path), "set-persona", "--role", "founder", "--force"]
    )
    assert result.exit_code == 0
    assert "schema_version: 1" in (tmp_path / "personality.md").read_text()
```

- [ ] **Step 2: Implement**

`src/cosinabox/cli/set_persona.py`:

```python
"""`cosinabox set-persona --role <name>`."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import click

AVAILABLE_PERSONAS = ("founder",)


@click.command("set-persona")
@click.option("--role", required=True, type=click.Choice(AVAILABLE_PERSONAS))
@click.option("--force", is_flag=True)
@click.pass_context
def set_persona_cmd(ctx: click.Context, role: str, force: bool) -> None:
    config_dir: Path = ctx.obj["config_dir"]
    target = config_dir / "personality.md"
    if target.exists() and not force:
        raise click.ClickException(
            f"{target} already exists. Pass --force to overwrite."
        )
    template_text = (
        files("cosinabox.personas").joinpath(f"{role}.md").read_text()
    )
    target.write_text(template_text)
    click.echo(f"Wrote {target} from persona template '{role}'")
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_cli_set_persona.py -v
git add src/cosinabox/cli/set_persona.py src/cosinabox/cli/main.py tests/unit/test_cli_set_persona.py
git commit -m "feat(cli): set-persona (Plan 1, Task T4.5)"
```

---

### Task T4.6: `cosinabox migrate` command

**Est:** 2 hr

**Files:**
- Create: `src/cosinabox/cli/migrate.py`
- Create: `src/cosinabox/migrations/__init__.py`
- Create: `src/cosinabox/migrations/registry.py`
- Modify: `src/cosinabox/cli/main.py`
- Create: `tests/unit/test_cli_migrate.py`

`cosinabox migrate` walks each user config file forward to the engine's current schema version. v0.1 schema is 1 — no migrations exist yet — so the command no-ops with `"All schemas current."`. The framework still ships now so future versions can register migrations.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_cli_migrate.py`:

```python
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli


def _seed(tmp: Path) -> None:
    (tmp / "personality.md").write_text(
        "---\nschema_version: 1\nname: A\ntimezone: UTC\n---\n\n# Voice\nbe brief\n"
    )
    (tmp / "stakeholders.yaml").write_text("schema_version: 1\nstakeholders: []\n")
    (tmp / "jobs.yaml").write_text("schema_version: 1\njobs: {}\n")
    (tmp / "integrations.yaml").write_text("schema_version: 1\nintegrations: {}\n")


def test_migrate_noops_at_current_version(tmp_path: Path) -> None:
    _seed(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "migrate"])
    assert result.exit_code == 0
    assert "current" in result.output.lower() or "no migrations" in result.output.lower()


def test_migrate_detects_outdated_schema(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / "stakeholders.yaml").write_text(
        "schema_version: 0\nstakeholders: []\n"
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "migrate"])
    # No registered migration from 0 → 1 in v0.1, so this should warn but not crash
    assert "stakeholders.yaml" in result.output
```

- [ ] **Step 2: Implement migration framework**

`src/cosinabox/migrations/__init__.py`:

```python
"""Schema migrations registry."""
```

`src/cosinabox/migrations/registry.py`:

```python
"""Migration registry: maps (file, from_version) -> migration callable."""

from __future__ import annotations

from typing import Callable

CURRENT_SCHEMA_VERSION = 1

# Empty for v0.1. Future versions register here:
# REGISTRY[("stakeholders.yaml", 1)] = migrate_stakeholders_1_to_2
REGISTRY: dict[tuple[str, int], Callable[[dict], dict]] = {}
```

`src/cosinabox/cli/migrate.py`:

```python
"""`cosinabox migrate`."""

from __future__ import annotations

import re
from pathlib import Path

import click
import yaml

from cosinabox.migrations.registry import CURRENT_SCHEMA_VERSION, REGISTRY

_FRONT = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def _read_version(path: Path) -> int | None:
    if path.suffix == ".md":
        m = _FRONT.match(path.read_text())
        if not m:
            return None
        front = yaml.safe_load(m.group(1))
        return front.get("schema_version")
    data = yaml.safe_load(path.read_text())
    return data.get("schema_version") if isinstance(data, dict) else None


@click.command("migrate")
@click.pass_context
def migrate_cmd(ctx: click.Context) -> None:
    """Walk schema_version forward on every config file."""
    config_dir: Path = ctx.obj["config_dir"]
    files = ["personality.md", "stakeholders.yaml", "jobs.yaml", "integrations.yaml"]
    any_outdated = False
    for fname in files:
        path = config_dir / fname
        if not path.exists():
            continue
        v = _read_version(path)
        if v is None:
            click.echo(f"{fname}: no schema_version field, skipping")
            continue
        if v == CURRENT_SCHEMA_VERSION:
            click.echo(f"{fname}: current (v{v})")
            continue
        any_outdated = True
        # Walk migrations
        cur = v
        while cur < CURRENT_SCHEMA_VERSION:
            mig = REGISTRY.get((fname, cur))
            if mig is None:
                click.echo(
                    f"{fname}: outdated (v{cur} → v{CURRENT_SCHEMA_VERSION}), "
                    f"no migration registered"
                )
                break
            click.echo(f"{fname}: applying {fname} v{cur} → v{cur+1}")
            cur += 1
    if not any_outdated:
        click.echo("All schemas current.")
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_cli_migrate.py -v
git add src/cosinabox/cli/migrate.py src/cosinabox/migrations src/cosinabox/cli/main.py tests/unit/test_cli_migrate.py
git commit -m "feat(cli): cosinabox migrate framework (Plan 1, Task T4.6)"
```

---

### Task T4.7: `cosinabox upgrade-docs` command

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/cli/upgrade_docs.py`
- Modify: `src/cosinabox/cli/main.py`
- Create: `tests/unit/test_cli_upgrade_docs.py`

Re-syncs `docs/agent/*.md` and `.cosinabox/` from the engine's bundled template into the user repo. Backs up any modified files to `.cosinabox/backup-<timestamp>/` before overwriting.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_cli_upgrade_docs.py`:

```python
from __future__ import annotations

import shutil
from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "src" / "cosinabox" / "templates" / "user-repo"


def test_upgrade_docs_refreshes_subdocs(tmp_path: Path) -> None:
    shutil.copytree(TEMPLATE, tmp_path / "cos")
    user = tmp_path / "cos"
    safety = user / "docs" / "agent" / "safety.md"
    safety.write_text("STALE STALE STALE")
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(user), "upgrade-docs"])
    assert result.exit_code == 0
    assert "STALE STALE STALE" not in safety.read_text()
    backups = list((user / ".cosinabox").glob("backup-*"))
    assert len(backups) == 1
```

- [ ] **Step 2: Implement**

`src/cosinabox/cli/upgrade_docs.py`:

```python
"""`cosinabox upgrade-docs` — refresh docs/agent/* and .cosinabox/ from the engine."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import click

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1] / "templates" / "user-repo"
)

REFRESH_PATHS = (
    "docs/agent/safety.md",
    "docs/agent/persona-interview.md",
    "docs/agent/editing-config.md",
    "docs/agent/adding-custom-jobs.md",
    "docs/agent/oauth-walkthrough.md",
    "docs/agent/proactive-suggestions.md",
    "BEST_PRACTICES.md",
    "CLAUDE.md",
    ".cosinabox/pre-commit",
    ".cosinabox/install-hook.sh",
    ".cosinabox/README.md",
)


@click.command("upgrade-docs")
@click.pass_context
def upgrade_docs_cmd(ctx: click.Context) -> None:
    config_dir: Path = ctx.obj["config_dir"]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_dir = config_dir / ".cosinabox" / f"backup-{ts}"
    backed_up = 0
    for rel in REFRESH_PATHS:
        src = TEMPLATE_ROOT / rel
        dst = config_dir / rel
        if not src.exists():
            continue
        if dst.exists() and dst.read_bytes() != src.read_bytes():
            backup_path = backup_dir / rel
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, backup_path)
            backed_up += 1
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    click.echo(f"Refreshed {len(REFRESH_PATHS)} files. {backed_up} backed up.")
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_cli_upgrade_docs.py -v
git add src/cosinabox/cli/upgrade_docs.py src/cosinabox/cli/main.py tests/unit/test_cli_upgrade_docs.py
git commit -m "feat(cli): cosinabox upgrade-docs (Plan 1, Task T4.7)"
```

---

### Task T4.8: `cosinabox auth google` command

**Est:** 2 hr

**Files:**
- Create: `src/cosinabox/cli/auth_google.py`
- Modify: `src/cosinabox/cli/main.py`
- Create: `tests/unit/test_cli_auth_google.py`

Runs the OAuth installed-app flow against `GOOGLE_OAUTH_CLIENT_ID` + `GOOGLE_OAUTH_CLIENT_SECRET`, prints the resulting refresh token. Tests mock the underlying `google_auth_oauthlib.InstalledAppFlow`.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_cli_auth_google.py`:

```python
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from cosinabox.cli.main import cli


def test_auth_google_prints_refresh_token() -> None:
    fake_flow = MagicMock()
    fake_creds = MagicMock(refresh_token="r-token-1")
    fake_flow.run_local_server.return_value = fake_creds
    with patch.dict(
        os.environ,
        {"GOOGLE_OAUTH_CLIENT_ID": "cid", "GOOGLE_OAUTH_CLIENT_SECRET": "sec"},
        clear=True,
    ):
        with patch(
            "cosinabox.cli.auth_google.InstalledAppFlow.from_client_config",
            return_value=fake_flow,
        ):
            runner = CliRunner()
            result = runner.invoke(cli, ["auth", "google"])
    assert result.exit_code == 0
    assert "r-token-1" in result.output


def test_auth_google_errors_without_env() -> None:
    with patch.dict(os.environ, {}, clear=True):
        runner = CliRunner()
        result = runner.invoke(cli, ["auth", "google"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Implement**

`src/cosinabox/cli/auth_google.py`:

```python
"""`cosinabox auth google` — mint a Google OAuth refresh token."""

from __future__ import annotations

import os

import click

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    InstalledAppFlow = None  # type: ignore[assignment]


SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]


@click.group("auth")
def auth_cmd() -> None:
    """Authentication helpers."""


@auth_cmd.command("google")
def auth_google_cmd() -> None:
    """Open the OAuth flow and print the refresh token."""
    if InstalledAppFlow is None:
        raise click.ClickException(
            "cosinabox[google] extra is required. "
            "Run: pip install 'cosinabox[google]'"
        )
    cid = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    if not cid or not secret:
        raise click.ClickException(
            "GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be set."
        )
    client_config = {
        "installed": {
            "client_id": cid,
            "client_secret": secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)
    click.echo("")
    click.echo("Save this to .env:")
    click.echo(f"GOOGLE_OAUTH_REFRESH_TOKEN={creds.refresh_token}")
```

Register `auth_cmd` (a Click *group*) in `cli/main.py`:

```python
from cosinabox.cli.auth_google import auth_cmd
cli.add_command(auth_cmd)
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_cli_auth_google.py -v
git add src/cosinabox/cli/auth_google.py src/cosinabox/cli/main.py tests/unit/test_cli_auth_google.py
git commit -m "feat(cli): cosinabox auth google (Plan 1, Task T4.8)"
```

---

### Task T4.9: Interview state machine (engine)

**Est:** 4 hr

**Files:**
- Create: `src/cosinabox/interview/__init__.py`
- Create: `src/cosinabox/interview/state_machine.py`
- Create: `src/cosinabox/interview/steps.py`
- Create: `tests/unit/test_interview_state_machine.py`

The state machine owns the 10-step interview. State persists in `.cosinabox/interview-state.json` so the agent can resume across sessions. Each step is a class with: `prompt() -> str`, `validate(answer) -> bool`, `apply(answer, config_dir) -> None`. Steps run in fixed order; the machine advances when a step's `apply` succeeds.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_interview_state_machine.py`:

```python
from __future__ import annotations

from pathlib import Path

import yaml

from cosinabox.interview.state_machine import InterviewMachine


def test_machine_starts_at_step_1(tmp_path: Path) -> None:
    m = InterviewMachine(config_dir=tmp_path)
    m.start()
    q = m.next_question()
    assert "name" in q.lower() or "identity" in q.lower()
    assert m.current_step_index == 0


def test_step_1_writes_personality_frontmatter(tmp_path: Path) -> None:
    m = InterviewMachine(config_dir=tmp_path)
    m.start()
    m.answer("Alex Smith, Founder, Loop AI, America/Los_Angeles")
    text = (tmp_path / "personality.md").read_text()
    assert "Alex Smith" in text
    assert "America/Los_Angeles" in text


def test_machine_completes_after_10_steps(tmp_path: Path) -> None:
    m = InterviewMachine(config_dir=tmp_path)
    m.start()
    canned_answers = [
        "Alex, Founder, Loop AI, America/Los_Angeles",
        "Closing a Series A in 6 weeks.",
        "blunt",
        "Sarah Chen, Sequoia, weekly, replies in mornings",
        "skip lunch and focus blocks",
        "yes, only morning_briefing and pre_meeting_prep",
        "done",  # OAuth — agent confirms it walked the user through the doc
        "yes default cap",
        "ok",  # show simulation
        "yes deploy",
    ]
    for a in canned_answers:
        m.answer(a)
    assert m.is_complete()
    # Verify side effects
    assert (tmp_path / "personality.md").exists()
    sk = yaml.safe_load((tmp_path / "stakeholders.yaml").read_text())
    assert any(s["name"] == "Sarah Chen" for s in sk["stakeholders"])
```

- [ ] **Step 2: Implement steps**

`src/cosinabox/interview/__init__.py`:

```python
"""Interview state machine."""
```

`src/cosinabox/interview/steps.py`:

```python
"""Interview step definitions."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

import yaml


class Step(ABC):
    name: str

    @abstractmethod
    def prompt(self) -> str: ...

    @abstractmethod
    def apply(self, answer: str, config_dir: Path) -> None: ...


class IdentityStep(Step):
    name = "identity"

    def prompt(self) -> str:
        return (
            "Step 1/10 — Identity. "
            "Tell me your name, role, company, and timezone "
            "(comma-separated, e.g. 'Alex, Founder, Loop AI, America/Los_Angeles')."
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        parts = [p.strip() for p in answer.split(",", 3)]
        while len(parts) < 4:
            parts.append("")
        name, role, company, tz = parts
        text = (
            f"---\nschema_version: 1\nname: {name}\n"
            f"role: {role} at {company}\ntimezone: {tz}\n---\n\n"
            f"# Voice\n(filled in by step 3)\n\n"
            f"# Stakes\n(filled in by step 2)\n\n"
            f"# Defaults\n- Default to bullets, not paragraphs\n"
        )
        (config_dir / "personality.md").write_text(text)


class StakesStep(Step):
    name = "stakes"

    def prompt(self) -> str:
        return (
            "Step 2/10 — Stakes. "
            "What's the most important thing happening in your work over "
            "the next 6 weeks? A CoS without stakes is a chatbot."
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        path = config_dir / "personality.md"
        text = path.read_text()
        text = re.sub(
            r"# Stakes\n.*?(\n#|\Z)",
            f"# Stakes\n{answer}\n\\1",
            text,
            count=1,
            flags=re.DOTALL,
        )
        path.write_text(text)


class VoiceStep(Step):
    name = "voice"

    def prompt(self) -> str:
        return (
            "Step 3/10 — Voice. "
            "Pick one: blunt / warm / analytical / formal / playful. "
            "Pick a runner-up if you want."
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        path = config_dir / "personality.md"
        text = path.read_text()
        text = re.sub(
            r"# Voice\n.*?(\n#)",
            f"# Voice\nYou are my Chief of Staff. Be {answer.strip()}.\n\\1",
            text,
            count=1,
            flags=re.DOTALL,
        )
        path.write_text(text)


class StakeholdersStep(Step):
    name = "stakeholders"

    def prompt(self) -> str:
        return (
            "Step 4/10 — Top stakeholders. "
            "Name your 5 most important people right now. For each, give "
            "name, role, cadence (daily/weekly/biweekly/monthly), and one note. "
            "Format: 'Name, Role, cadence, note' — one per line, or just one to start."
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        path = config_dir / "stakeholders.yaml"
        existing = (
            yaml.safe_load(path.read_text())
            if path.exists()
            else {"schema_version": 1, "stakeholders": []}
        )
        for line in answer.splitlines():
            parts = [p.strip() for p in line.split(",", 3)]
            if len(parts) < 3:
                continue
            name, role, cadence = parts[:3]
            note = parts[3] if len(parts) > 3 else ""
            existing["stakeholders"].append(
                {"name": name, "role": role, "cadence": cadence,
                 "last_contact": "2026-01-01", "notes": note}
            )
        path.write_text(yaml.safe_dump(existing, sort_keys=False))


class CalendarRealityStep(Step):
    name = "calendar_reality"

    def prompt(self) -> str:
        return (
            "Step 5/10 — Calendar reality. "
            "What should pre-meeting prep skip? Common: 'lunch', 'focus block', "
            "'1:1'. Comma-separated, or 'none'."
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        path = config_dir / "jobs.yaml"
        data = (
            yaml.safe_load(path.read_text())
            if path.exists()
            else {"schema_version": 1, "jobs": {}}
        )
        skips = [] if answer.strip().lower() == "none" else [
            s.strip() for s in answer.split(",") if s.strip()
        ]
        data["jobs"].setdefault("pre_meeting_prep", {"enabled": True})
        data["jobs"]["pre_meeting_prep"]["skip_if_calendar_title_matches"] = skips
        path.write_text(yaml.safe_dump(data, sort_keys=False))


class JobStagingStep(Step):
    name = "job_staging"

    def prompt(self) -> str:
        return (
            "Step 6/10 — Job staging. "
            "For week 1, I'm enabling only morning_briefing and pre_meeting_prep. "
            "Sound good? (yes/no)"
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        path = config_dir / "jobs.yaml"
        data = (
            yaml.safe_load(path.read_text())
            if path.exists()
            else {"schema_version": 1, "jobs": {}}
        )
        for j in ("morning_briefing", "pre_meeting_prep"):
            data["jobs"].setdefault(j, {})
            data["jobs"][j]["enabled"] = True
        for j in ("evening_wrap", "weekly_review", "followup_reminder"):
            data["jobs"].setdefault(j, {})
            data["jobs"][j]["enabled"] = False
        data["jobs"]["morning_briefing"].setdefault("schedule", "0 8 * * *")
        path.write_text(yaml.safe_dump(data, sort_keys=False))


class OAuthStep(Step):
    name = "oauth"

    def prompt(self) -> str:
        return (
            "Step 7/10 — API keys + OAuth. "
            "Walk through docs/agent/oauth-walkthrough.md with me. "
            "When you've finished and have GOOGLE_OAUTH_REFRESH_TOKEN in .env, say 'done'."
        )

    def apply(self, answer: str, config_dir: Path) -> None:  # noqa: ARG002
        # No file writes — the user did the work in .env. Acknowledged by saying 'done'.
        pass


class BudgetStep(Step):
    name = "budget"

    def prompt(self) -> str:
        return (
            "Step 8/10 — Budget caps. "
            "Default daily cap is $15. Want to change? "
            "(say 'yes default cap' or give a number like '$25')"
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        # v0.1 stores cap in .env (COSINABOX_DAILY_CAP_USD); ignore for now
        # if user says default. Future versions may persist to a config file.
        pass


class FirstSimulationStep(Step):
    name = "first_simulation"

    def prompt(self) -> str:
        return (
            "Step 9/10 — First simulation. "
            "I'm about to run `cosinabox simulate morning_briefing --fixture=sample` "
            "and show you the output. Ready?"
        )

    def apply(self, answer: str, config_dir: Path) -> None:  # noqa: ARG002
        # Agent runs the actual simulate command externally.
        pass


class DeployStep(Step):
    name = "deploy"

    def prompt(self) -> str:
        return (
            "Step 10/10 — Deploy. "
            "I'll walk you through the Railway template + GitHub repo connect "
            "+ env var entry. Ready? (yes/no)"
        )

    def apply(self, answer: str, config_dir: Path) -> None:  # noqa: ARG002
        # Deployment is external; this step is acknowledgement.
        pass


STEPS: list[Step] = [
    IdentityStep(),
    StakesStep(),
    VoiceStep(),
    StakeholdersStep(),
    CalendarRealityStep(),
    JobStagingStep(),
    OAuthStep(),
    BudgetStep(),
    FirstSimulationStep(),
    DeployStep(),
]
```

`src/cosinabox/interview/state_machine.py`:

```python
"""Interview state machine — owns the 10-step interview."""

from __future__ import annotations

import json
from pathlib import Path

from cosinabox.interview.steps import STEPS

STATE_FILENAME = ".cosinabox/interview-state.json"


class InterviewMachine:
    def __init__(self, *, config_dir: Path) -> None:
        self.config_dir = Path(config_dir)
        self.current_step_index = 0
        self._completed = False

    def start(self) -> None:
        self.current_step_index = 0
        self._completed = False
        (self.config_dir / ".cosinabox").mkdir(parents=True, exist_ok=True)
        self._persist()

    def next_question(self) -> str:
        if self.is_complete():
            return "INTERVIEW COMPLETE"
        return STEPS[self.current_step_index].prompt()

    def answer(self, text: str) -> None:
        if self.is_complete():
            return
        STEPS[self.current_step_index].apply(text, self.config_dir)
        self.current_step_index += 1
        if self.current_step_index >= len(STEPS):
            self._completed = True
        self._persist()

    def is_complete(self) -> bool:
        return self._completed

    def _persist(self) -> None:
        path = self.config_dir / STATE_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"index": self.current_step_index, "complete": self._completed}
            )
        )

    @classmethod
    def resume(cls, *, config_dir: Path) -> "InterviewMachine":
        m = cls(config_dir=config_dir)
        path = config_dir / STATE_FILENAME
        if path.exists():
            state = json.loads(path.read_text())
            m.current_step_index = state["index"]
            m._completed = state["complete"]
        return m
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_interview_state_machine.py -v
ruff check src/cosinabox/interview tests/unit/test_interview_state_machine.py
mypy src/cosinabox/interview
git add src/cosinabox/interview tests/unit/test_interview_state_machine.py
git commit -m "feat(interview): 10-step state machine (Plan 1, Task T4.9)"
```

---

### Task T4.10: `cosinabox interview` CLI

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/cli/interview.py`
- Modify: `src/cosinabox/cli/main.py`
- Create: `tests/integration/test_cli_interview.py`

CLI surface:
- `cosinabox interview --start` → prints first question
- `cosinabox interview --answer "..."` → applies answer, prints next question
- `cosinabox interview --status` → prints current step number + progress

- [ ] **Step 1: Write the failing test**

`tests/integration/test_cli_interview.py`:

```python
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli


def test_interview_start_then_answer(tmp_path: Path) -> None:
    runner = CliRunner()
    r1 = runner.invoke(cli, ["-C", str(tmp_path), "interview", "--start"])
    assert r1.exit_code == 0
    assert "Step 1/10" in r1.output
    r2 = runner.invoke(
        cli,
        ["-C", str(tmp_path), "interview", "--answer",
         "Alex, Founder, Loop, UTC"],
    )
    assert r2.exit_code == 0
    assert "Step 2/10" in r2.output or "Stakes" in r2.output
    assert (tmp_path / "personality.md").exists()
```

- [ ] **Step 2: Implement**

`src/cosinabox/cli/interview.py`:

```python
"""`cosinabox interview` — drive the 10-step interview."""

from __future__ import annotations

from pathlib import Path

import click

from cosinabox.interview.state_machine import InterviewMachine


@click.command("interview")
@click.option("--start", is_flag=True, help="Begin a new interview.")
@click.option("--answer", default=None, help="Answer the current question.")
@click.option("--status", is_flag=True, help="Show progress.")
@click.pass_context
def interview_cmd(
    ctx: click.Context, start: bool, answer: str | None, status: bool
) -> None:
    config_dir: Path = ctx.obj["config_dir"]
    if start:
        m = InterviewMachine(config_dir=config_dir)
        m.start()
        click.echo(m.next_question())
        return
    m = InterviewMachine.resume(config_dir=config_dir)
    if status:
        click.echo(
            f"Step {m.current_step_index + 1}/10 "
            f"{'(complete)' if m.is_complete() else ''}"
        )
        return
    if answer is not None:
        m.answer(answer)
        click.echo(m.next_question())
        return
    click.echo(m.next_question())
```

Register in `cli/main.py`.

- [ ] **Step 3: Run + commit**

```bash
pytest tests/integration/test_cli_interview.py -v
git add src/cosinabox/cli/interview.py src/cosinabox/cli/main.py tests/integration/test_cli_interview.py
git commit -m "feat(cli): cosinabox interview --start/--answer/--status (Plan 1, Task T4.10)"
```

---

### Task T4.11: `cosinabox test` command

**Est:** 15 min

**Files:**
- Create: `src/cosinabox/cli/test_runner.py`
- Modify: `src/cosinabox/cli/main.py`

A thin wrapper around pytest that sets `PYTHONPATH` to include `custom_jobs/` (so users can `import` their custom jobs in tests). One-liner; no test (it's a passthrough).

- [ ] **Step 1: Implement**

`src/cosinabox/cli/test_runner.py`:

```python
"""`cosinabox test` — wraps pytest with custom_jobs/ on the path."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import click


@click.command("test")
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def test_cmd(ctx: click.Context, pytest_args: tuple[str, ...]) -> None:
    config_dir: Path = ctx.obj["config_dir"]
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        f"{config_dir}{os.pathsep}{env.get('PYTHONPATH', '')}"
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *pytest_args],
        cwd=config_dir,
        env=env,
    )
    ctx.exit(result.returncode)
```

- [ ] **Step 2: Commit**

```bash
git add src/cosinabox/cli/test_runner.py src/cosinabox/cli/main.py
git commit -m "feat(cli): cosinabox test wrapper (Plan 1, Task T4.11)"
```

---

### Task T4.12: Doctor framework + check 1 (personality_thin)

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/doctor/__init__.py`
- Create: `src/cosinabox/doctor/checks.py`
- Create: `src/cosinabox/doctor/registry.py`
- Create: `tests/unit/test_doctor_personality_thin.py`

The doctor framework lets each check be a class with `name`, `severity`, `run(config_dir, history) -> CheckResult`. The registry collects them; `cosinabox doctor` (T4.20) iterates the registry and emits results.

This task implements the framework + the first check (`personality_thin`). Subsequent tasks T4.13-T4.19 each add one more check using the same pattern.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_doctor_personality_thin.py`:

```python
from __future__ import annotations

from pathlib import Path

from cosinabox.doctor.checks import PersonalityThinCheck


def test_thin_personality_flagged(tmp_path: Path) -> None:
    (tmp_path / "personality.md").write_text(
        "---\nschema_version: 1\nname: A\ntimezone: UTC\n---\n\n# Voice\nbe direct\n"
    )
    check = PersonalityThinCheck()
    result = check.run(config_dir=tmp_path, history={})
    assert result.status == "fail"
    assert "personality" in result.message.lower()


def test_substantive_personality_passes(tmp_path: Path) -> None:
    body = "x" * 800
    (tmp_path / "personality.md").write_text(
        f"---\nschema_version: 1\nname: A\ntimezone: UTC\n---\n\n# Voice\n{body}\n"
    )
    check = PersonalityThinCheck()
    result = check.run(config_dir=tmp_path, history={})
    assert result.status == "pass"
```

- [ ] **Step 2: Implement framework**

`src/cosinabox/doctor/__init__.py`:

```python
"""cosinabox doctor — health checks."""
```

`src/cosinabox/doctor/checks.py`:

```python
"""Doctor check definitions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cosinabox import defaults


@dataclass
class CheckResult:
    name: str
    status: str  # "pass" | "fail" | "warn"
    message: str


class Check(ABC):
    name: str
    severity: str = "warn"

    @abstractmethod
    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult: ...


class PersonalityThinCheck(Check):
    name = "personality_thin"
    severity = "warn"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:  # noqa: ARG002
        path = config_dir / "personality.md"
        if not path.exists():
            return CheckResult(self.name, "fail", "personality.md missing")
        text = path.read_text()
        if len(text) < defaults.DOCTOR_PERSONALITY_MIN_CHARS:
            return CheckResult(
                self.name,
                "fail",
                f"personality.md is {len(text)} chars; "
                f"under threshold of {defaults.DOCTOR_PERSONALITY_MIN_CHARS}. "
                "Generic personality = generic briefings.",
            )
        return CheckResult(self.name, "pass", "personality is substantive")
```

`src/cosinabox/doctor/registry.py`:

```python
"""Doctor check registry."""

from __future__ import annotations

from cosinabox.doctor.checks import Check, PersonalityThinCheck

REGISTRY: list[Check] = [
    PersonalityThinCheck(),
    # T4.13-T4.19 append the rest
]
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_doctor_personality_thin.py -v
git add src/cosinabox/doctor tests/unit/test_doctor_personality_thin.py
git commit -m "feat(doctor): framework + personality_thin check (Plan 1, Task T4.12)"
```

---

### Task T4.13: Doctor checks 2-4 (stakeholders_empty, cost_runaway, tool_loop_excess)

**Est:** 1.5 hr

**Files:**
- Modify: `src/cosinabox/doctor/checks.py` (add 3 classes)
- Modify: `src/cosinabox/doctor/registry.py`
- Create: `tests/unit/test_doctor_checks_2_to_4.py`

Each check is the same shape as `PersonalityThinCheck`. The `history` dict passed to `run()` is a placeholder for spend/iteration data the doctor command will populate (cost spend per day, average tool iterations per message). For v0.1, the history is loaded from a JSON file in `.cosinabox/history.json` (empty if not present, in which case the cost/loop checks no-op with a "no data" warning).

- [ ] **Step 1: Write the failing test**

`tests/unit/test_doctor_checks_2_to_4.py`:

```python
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from cosinabox.doctor.checks import (
    CostRunawayCheck,
    StakeholdersEmptyCheck,
    ToolLoopExcessCheck,
)


def test_stakeholders_empty_after_7_days(tmp_path: Path) -> None:
    (tmp_path / "stakeholders.yaml").write_text(
        "schema_version: 1\nstakeholders:\n  - name: A\n    cadence: weekly\n"
    )
    check = StakeholdersEmptyCheck()
    history = {"installed_date": (date.today() - timedelta(days=10)).isoformat()}
    result = check.run(config_dir=tmp_path, history=history)
    assert result.status == "fail"


def test_stakeholders_empty_passes_with_3(tmp_path: Path) -> None:
    body = "schema_version: 1\nstakeholders:\n"
    for n in ("A", "B", "C"):
        body += f"  - name: {n}\n    cadence: weekly\n"
    (tmp_path / "stakeholders.yaml").write_text(body)
    check = StakeholdersEmptyCheck()
    history = {"installed_date": (date.today() - timedelta(days=10)).isoformat()}
    result = check.run(config_dir=tmp_path, history=history)
    assert result.status == "pass"


def test_cost_runaway_flagged(tmp_path: Path) -> None:
    history = {
        "daily_spend": {
            (date.today() - timedelta(days=i)).isoformat(): 13.0 for i in range(7)
        }
    }
    check = CostRunawayCheck()
    result = check.run(config_dir=tmp_path, history=history)
    assert result.status == "fail"


def test_tool_loop_excess_flagged(tmp_path: Path) -> None:
    history = {"avg_tool_iterations_per_message": 7.5}
    check = ToolLoopExcessCheck()
    result = check.run(config_dir=tmp_path, history=history)
    assert result.status == "fail"
```

- [ ] **Step 2: Append to `src/cosinabox/doctor/checks.py`**

```python
import yaml
from datetime import date


class StakeholdersEmptyCheck(Check):
    name = "stakeholders_empty"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:
        path = config_dir / "stakeholders.yaml"
        if not path.exists():
            return CheckResult(self.name, "fail", "stakeholders.yaml missing")
        data = yaml.safe_load(path.read_text()) or {}
        count = len(data.get("stakeholders", []))
        installed = history.get("installed_date")
        if installed is None:
            return CheckResult(self.name, "warn", "no install date in history")
        days = (date.today() - date.fromisoformat(installed)).days
        if days >= defaults.DOCTOR_STAKEHOLDERS_MIN_AFTER_DAYS and count < defaults.DOCTOR_STAKEHOLDERS_MIN_COUNT:
            return CheckResult(
                self.name,
                "fail",
                f"only {count} stakeholders after {days} days; "
                f"followup_reminder won't have data",
            )
        return CheckResult(self.name, "pass", f"{count} stakeholders")


class CostRunawayCheck(Check):
    name = "cost_runaway"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:  # noqa: ARG002
        spend = history.get("daily_spend") or {}
        if not spend:
            return CheckResult(self.name, "warn", "no spend data yet")
        cap = defaults.COST_DAILY_CAP_USD
        threshold = cap * defaults.DOCTOR_COST_RUNAWAY_RATIO
        hot_days = [d for d, s in spend.items() if s > threshold]
        if hot_days:
            return CheckResult(
                self.name,
                "fail",
                f"{len(hot_days)} day(s) above {defaults.DOCTOR_COST_RUNAWAY_RATIO*100:.0f}% "
                f"of cap (${cap:.0f}/day)",
            )
        return CheckResult(self.name, "pass", "spend within cap")


class ToolLoopExcessCheck(Check):
    name = "tool_loop_excess"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:  # noqa: ARG002
        avg = history.get("avg_tool_iterations_per_message")
        if avg is None:
            return CheckResult(self.name, "warn", "no iteration data yet")
        if avg > defaults.DOCTOR_TOOL_LOOP_AVG_THRESHOLD:
            return CheckResult(
                self.name,
                "fail",
                f"avg {avg:.1f} tool iterations per message; "
                f"prompts may be too vague",
            )
        return CheckResult(self.name, "pass", f"avg {avg:.1f} iterations")
```

Add the new checks to `src/cosinabox/doctor/registry.py`:

```python
from cosinabox.doctor.checks import (
    PersonalityThinCheck,
    StakeholdersEmptyCheck,
    CostRunawayCheck,
    ToolLoopExcessCheck,
)

REGISTRY = [
    PersonalityThinCheck(),
    StakeholdersEmptyCheck(),
    CostRunawayCheck(),
    ToolLoopExcessCheck(),
]
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_doctor_checks_2_to_4.py -v
git add src/cosinabox/doctor tests/unit/test_doctor_checks_2_to_4.py
git commit -m "feat(doctor): stakeholders_empty + cost_runaway + tool_loop_excess (Plan 1, Task T4.13)"
```

---

### Task T4.14: Doctor checks 5-7 (prep_noise, briefing_drift, secret_in_tracked_file)

**Est:** 1.5 hr

**Files:**
- Modify: `src/cosinabox/doctor/checks.py` (3 classes)
- Modify: `src/cosinabox/doctor/registry.py`
- Create: `tests/unit/test_doctor_checks_5_to_7.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_doctor_checks_5_to_7.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path

from cosinabox.doctor.checks import (
    BriefingDriftCheck,
    PrepNoiseCheck,
    SecretInTrackedFileCheck,
)


def test_prep_noise_flagged() -> None:
    history = {"prep_fires_per_day": 12}
    check = PrepNoiseCheck()
    result = check.run(config_dir=Path("/tmp"), history=history)
    assert result.status == "fail"


def test_briefing_drift_when_override_unsimulated(tmp_path: Path) -> None:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "morning_briefing.md").write_text("custom prompt")
    history = {"simulate_log": []}
    check = BriefingDriftCheck()
    result = check.run(config_dir=tmp_path, history=history)
    assert result.status == "fail"


def test_secret_in_tracked_file_flagged(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    leaky = tmp_path / "personality.md"
    leaky.write_text("hello sk-ant-12345leakedkey end")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-m", "test", "--no-verify"],
        cwd=tmp_path, check=True, capture_output=True,
    )
    check = SecretInTrackedFileCheck()
    result = check.run(config_dir=tmp_path, history={})
    assert result.status == "fail"
```

- [ ] **Step 2: Implement the 3 checks**

Append to `src/cosinabox/doctor/checks.py`:

```python
import re
import subprocess


class PrepNoiseCheck(Check):
    name = "prep_noise"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:  # noqa: ARG002
        fires = history.get("prep_fires_per_day")
        if fires is None:
            return CheckResult(self.name, "warn", "no fire-rate data")
        if fires > defaults.DOCTOR_PREP_NOISE_PER_DAY:
            return CheckResult(
                self.name,
                "fail",
                f"pre_meeting_prep firing {fires}x per day; tune skip filters",
            )
        return CheckResult(self.name, "pass", f"{fires}/day")


class BriefingDriftCheck(Check):
    name = "briefing_drift"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:
        override = config_dir / "prompts" / "morning_briefing.md"
        if not override.exists():
            return CheckResult(self.name, "pass", "no override")
        sim_log = history.get("simulate_log") or []
        if "morning_briefing" not in sim_log:
            return CheckResult(
                self.name,
                "fail",
                "morning_briefing prompt overridden but never simulated; "
                "run `cosinabox simulate morning_briefing`",
            )
        return CheckResult(self.name, "pass", "override validated by simulate")


_SECRET_PATTERNS = re.compile(
    r"(sk-ant-[A-Za-z0-9_-]+|xoxb-[A-Za-z0-9-]+|"
    r"AIza[0-9A-Za-z_-]{35}|ghp_[A-Za-z0-9]{36})"
)


class SecretInTrackedFileCheck(Check):
    name = "secret_in_tracked_file"
    severity = "critical"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:  # noqa: ARG002
        try:
            ls = subprocess.run(
                ["git", "ls-files"],
                cwd=config_dir,
                capture_output=True, text=True, check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return CheckResult(self.name, "warn", "not a git repo")
        leaks: list[str] = []
        for relpath in ls.stdout.splitlines():
            full = config_dir / relpath
            try:
                text = full.read_text()
            except (UnicodeDecodeError, FileNotFoundError):
                continue
            if _SECRET_PATTERNS.search(text):
                leaks.append(relpath)
        if leaks:
            return CheckResult(
                self.name,
                "fail",
                f"possible secrets in: {', '.join(leaks)} — rotate immediately",
            )
        return CheckResult(self.name, "pass", "no secret patterns found")
```

Update registry to include the three new checks.

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_doctor_checks_5_to_7.py -v
git add src/cosinabox/doctor tests/unit/test_doctor_checks_5_to_7.py
git commit -m "feat(doctor): prep_noise + briefing_drift + secret_in_tracked_file (Plan 1, Task T4.14)"
```

---

### Task T4.15: Doctor checks 8-10 (stale_followups, oauth_expiring, schema_outdated)

**Est:** 1.5 hr

**Files:**
- Modify: `src/cosinabox/doctor/checks.py`
- Modify: `src/cosinabox/doctor/registry.py`
- Create: `tests/unit/test_doctor_checks_8_to_10.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/test_doctor_checks_8_to_10.py`:

```python
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from cosinabox.doctor.checks import (
    OAuthExpiringCheck,
    SchemaOutdatedCheck,
    StaleFollowupsCheck,
)


def test_stale_followups_flagged(tmp_path: Path) -> None:
    body = "schema_version: 1\nstakeholders:\n"
    for i in range(25):
        old = (date.today() - timedelta(days=60)).isoformat()
        body += f"  - name: P{i}\n    cadence: weekly\n    last_contact: '{old}'\n"
    (tmp_path / "stakeholders.yaml").write_text(body)
    check = StaleFollowupsCheck()
    result = check.run(config_dir=tmp_path, history={})
    assert result.status == "fail"


def test_oauth_expiring_flagged() -> None:
    history = {
        "google_token_expires": (date.today() + timedelta(days=7)).isoformat()
    }
    check = OAuthExpiringCheck()
    result = check.run(config_dir=Path("/tmp"), history=history)
    assert result.status == "fail"


def test_schema_outdated_flagged(tmp_path: Path) -> None:
    (tmp_path / "stakeholders.yaml").write_text("schema_version: 0\nstakeholders: []\n")
    check = SchemaOutdatedCheck()
    result = check.run(config_dir=tmp_path, history={})
    assert result.status == "fail"
```

- [ ] **Step 2: Implement**

Append to `src/cosinabox/doctor/checks.py`:

```python
class StaleFollowupsCheck(Check):
    name = "stale_followups"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:  # noqa: ARG002
        path = config_dir / "stakeholders.yaml"
        if not path.exists():
            return CheckResult(self.name, "warn", "no stakeholders.yaml")
        data = yaml.safe_load(path.read_text()) or {}
        from datetime import date as _date
        cadence_days = {"daily": 1, "weekly": 7, "biweekly": 14, "monthly": 30, "quarterly": 90}
        stale = 0
        for s in data.get("stakeholders", []):
            lc = s.get("last_contact")
            if not lc:
                continue
            days = (_date.today() - _date.fromisoformat(lc)).days
            cd = cadence_days.get(s.get("cadence", "weekly"), 7)
            if days > cd + defaults.FOLLOWUP_STALENESS_DAYS:
                stale += 1
        if stale > defaults.DOCTOR_STALE_FOLLOWUP_COUNT:
            return CheckResult(
                self.name,
                "fail",
                f"{stale} stakeholders past their cadence; "
                f"user may not be acting on briefings",
            )
        return CheckResult(self.name, "pass", f"{stale} stale")


class OAuthExpiringCheck(Check):
    name = "oauth_expiring"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:  # noqa: ARG002
        from datetime import date as _date
        expires = history.get("google_token_expires")
        if expires is None:
            return CheckResult(self.name, "warn", "no token expiry data")
        days_until = (_date.fromisoformat(expires) - _date.today()).days
        if days_until < defaults.DOCTOR_OAUTH_EXPIRY_WARN_DAYS:
            return CheckResult(
                self.name,
                "fail",
                f"Google OAuth refresh token expires in {days_until} days; "
                f"re-run `cosinabox auth google`",
            )
        return CheckResult(self.name, "pass", f"{days_until} days")


class SchemaOutdatedCheck(Check):
    name = "schema_outdated"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:  # noqa: ARG002
        from cosinabox.migrations.registry import CURRENT_SCHEMA_VERSION
        outdated: list[str] = []
        for fname in ("stakeholders.yaml", "jobs.yaml", "integrations.yaml"):
            path = config_dir / fname
            if not path.exists():
                continue
            data = yaml.safe_load(path.read_text()) or {}
            v = data.get("schema_version")
            if v is not None and v < CURRENT_SCHEMA_VERSION:
                outdated.append(f"{fname} (v{v})")
        if outdated:
            return CheckResult(
                self.name,
                "fail",
                f"outdated: {', '.join(outdated)} — run `cosinabox migrate`",
            )
        return CheckResult(self.name, "pass", "schemas current")
```

Update registry to register all 10.

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_doctor_checks_8_to_10.py -v
git add src/cosinabox/doctor tests/unit/test_doctor_checks_8_to_10.py
git commit -m "feat(doctor): stale_followups + oauth_expiring + schema_outdated (Plan 1, Task T4.15)"
```

---

### Task T4.16: `cosinabox doctor [--json]` CLI

**Est:** 1 hr

**Files:**
- Create: `src/cosinabox/cli/doctor.py`
- Modify: `src/cosinabox/cli/main.py`
- Create: `tests/unit/test_cli_doctor.py`

`cosinabox doctor` walks the registry and prints each check's status. `--json` outputs `[{name, status, message}, ...]`. Exit code is 0 if all pass/warn, 1 if any fail.

- [ ] **Step 1: Write the failing test**

`tests/unit/test_cli_doctor.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample-user-repo"


def test_doctor_runs_all_checks() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "doctor"])
    # exit code may be 0 or 1 depending on fixtures; we just want all 10 to run
    for n in (
        "personality_thin", "stakeholders_empty", "cost_runaway",
        "tool_loop_excess", "prep_noise", "briefing_drift",
        "secret_in_tracked_file", "stale_followups", "oauth_expiring",
        "schema_outdated",
    ):
        assert n in result.output


def test_doctor_json_mode_emits_list() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "doctor", "--json"])
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    assert len(parsed) == 10
    assert all("name" in r and "status" in r for r in parsed)
```

- [ ] **Step 2: Implement**

`src/cosinabox/cli/doctor.py`:

```python
"""`cosinabox doctor`."""

from __future__ import annotations

import json as jsonlib
from pathlib import Path

import click

from cosinabox.doctor.registry import REGISTRY


def _load_history(config_dir: Path) -> dict:
    path = config_dir / ".cosinabox" / "history.json"
    if path.exists():
        try:
            return jsonlib.loads(path.read_text())
        except jsonlib.JSONDecodeError:
            return {}
    return {}


@click.command("doctor")
@click.option("--json", "json_out", is_flag=True)
@click.pass_context
def doctor_cmd(ctx: click.Context, json_out: bool) -> None:
    """Run all health checks."""
    config_dir: Path = ctx.obj["config_dir"]
    history = _load_history(config_dir)
    results = [c.run(config_dir=config_dir, history=history) for c in REGISTRY]
    if json_out:
        click.echo(
            jsonlib.dumps(
                [{"name": r.name, "status": r.status, "message": r.message} for r in results],
                indent=2,
            )
        )
    else:
        for r in results:
            icon = {"pass": "OK", "warn": "WARN", "fail": "FAIL"}.get(r.status, "?")
            click.echo(f"[{icon}] {r.name}: {r.message}")
    if any(r.status == "fail" for r in results):
        ctx.exit(1)
```

Register in `cli/main.py`.

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/test_cli_doctor.py -v
git add src/cosinabox/cli/doctor.py src/cosinabox/cli/main.py tests/unit/test_cli_doctor.py
git commit -m "feat(cli): cosinabox doctor [--json] (Plan 1, Task T4.16)"
```

---

### Task T4.17: `--json` audit on read-oriented commands

**Est:** 1 hr

**Files:**
- Modify: `src/cosinabox/cli/describe.py` (already has --json from T4.1)
- Modify: `src/cosinabox/cli/validate.py` (already has --json from T2.11)
- Modify: `src/cosinabox/cli/doctor.py` (already has --json from T4.16)
- Create: `tests/integration/test_cli_json_audit.py`

The spec says every read-oriented command should support `--json`. Audit each existing read command and confirm `--json` works. Add the flag where missing.

- [ ] **Step 1: Write the failing test**

`tests/integration/test_cli_json_audit.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample-user-repo"


def test_validate_json_parses() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "validate", "--json"])
    json.loads(result.output)


def test_describe_json_parses() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "describe", "--json"])
    json.loads(result.output)


def test_doctor_json_parses() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "doctor", "--json"])
    json.loads(result.output)
```

- [ ] **Step 2: Run the test, fix any command that lacks --json**

```bash
pytest tests/integration/test_cli_json_audit.py -v
```

If any test fails because a command is missing `--json`, add the flag using the same pattern as `validate`/`describe`/`doctor`. As of T4.16 these three should already work; the test just enforces the contract going forward.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_cli_json_audit.py
git commit -m "test(cli): assert --json on every read-oriented command (Plan 1, Task T4.17)"
```

---

### Task T4.18: End-to-end integration test (init → interview → simulate → doctor)

**Est:** 1 hr

**Files:**
- Create: `tests/integration/test_e2e_setup.py`

This is the milestone's smoke test. It walks the entire user journey end-to-end against a temp directory.

- [ ] **Step 1: Write the test**

`tests/integration/test_e2e_setup.py`:

```python
from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli


def test_init_then_interview_then_simulate_then_doctor(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runner = CliRunner()

    # 1. Init
    target = tmp_path / "my-cos"
    r = runner.invoke(cli, ["init", str(target)])
    assert r.exit_code == 0

    # 2. Interview, walking all 10 steps
    r = runner.invoke(cli, ["-C", str(target), "interview", "--start"])
    assert r.exit_code == 0
    canned = [
        "Alex, Founder, Loop AI, America/Los_Angeles",
        "Closing a Series A in 6 weeks. Every conversation either moves us toward signed term sheets or it doesn't.",
        "blunt",
        "Sarah Chen, Lead investor at Sequoia, weekly, replies in mornings\nDavid Park, Co-founder, daily, sync constantly",
        "lunch, focus block",
        "yes",
        "done",
        "yes default",
        "ok",
        "yes",
    ]
    for ans in canned:
        r = runner.invoke(cli, ["-C", str(target), "interview", "--answer", ans])
        assert r.exit_code == 0, r.output

    # 3. Simulate
    r = runner.invoke(
        cli, ["-C", str(target), "simulate", "morning_briefing", "--fixture=sample"]
    )
    assert r.exit_code == 0, r.output

    # 4. Doctor
    r = runner.invoke(cli, ["-C", str(target), "doctor", "--json"])
    import json
    data = json.loads(r.output)
    assert len(data) == 10
```

- [ ] **Step 2: Run + commit**

```bash
pytest tests/integration/test_e2e_setup.py -v
git add tests/integration/test_e2e_setup.py
git commit -m "test(e2e): init → interview → simulate → doctor walkthrough (Plan 1, Task T4.18)"
```

---

### Task T4.19: M4 verification + PR

**Est:** 30 min

- [ ] **Step 1: Full suite**

```bash
ruff check src tests
ruff format --check src tests
mypy src/cosinabox
pytest -q
```

- [ ] **Step 2: Push, PR, auto-merge**

```bash
git push
gh pr create --title "Plan 1 Milestone 4: CLI + interview + doctor" --body "$(cat <<'EOF'
## Summary
Lands every CLI command from spec section 5 (describe, add-stakeholder, set-job-schedule, enable/disable-job, set-persona, migrate, upgrade-docs, auth google, test, doctor, interview), the 10-step interview state machine, and all 10 doctor checks. End-to-end test walks init → interview → simulate → doctor.

## Test plan
- [ ] Every command has a unit or integration test
- [ ] doctor --json returns 10 results
- [ ] e2e test passes against a temp directory
EOF
)"
gh pr merge --auto --squash --delete-branch
```

- [ ] **Step 3: Write Plan 1 retro**

After M4 merges, write the **plan-level retro** (covers all of Plan 1, not just M4). Use `docs/retros/RETRO_TEMPLATE.md`. Name: `docs/retros/2026-XX-XX-cosinabox-plan-1-retro.md`. Include:

- What shipped vs what was planned (look at every M-level "Done when" criterion)
- Estimate calibration: which tasks overshot, which undershot, by how much
- Discipline commitments: did any get violated? (worktree-at-start, per-task commits, retros, brainstorm-first, etc.)
- New lessons that should become memory notes or new commitments
- Decisions for Plan 2 (rovik-keevs migration): schema bumps needed? new defaults? additional checks?

The retro is the input for writing Plan 2 in a separate session.

---

## Self-review

After completing all tasks above, run this checklist on the plan itself.

**Spec coverage:** Every item in spec section "v0.1 Deliverables Summary" that's marked for M1-M4 has a task. The migration deliverables section is **deferred to Plan 2** by design and not covered here. Public launch deliverables (PyPI publish, Docker registry, GitHub public, README, AGENTS.md, CONTRIBUTING.md, OUT_OF_SCOPE.md, .github/FUNDING.yml, SPONSORS.md, issue template) are **deferred to Plan 3** by design.

**Placeholder scan:** No "TBD", "TODO", "implement later", or step that lacks the actual code.

**Type consistency:**
- `Memory` (T1.3) — `store_message`, `recent_messages`, `clear_old`, `close`. Used by no other M1 task directly.
- `CostTracker` (T1.4) — `check_message_cost`, `record`, `spend_on`. Used by `AgentLoop` (T1.6).
- `Router` (T1.5) — `choose_model`, `tools_for_channel`. Used by `AgentLoop`.
- `AgentLoop` (T1.6) — `run(prompt, session_id) -> LoopResult`. Used by every job (T2.3-T2.7).
- `Job` (T2.2) base + `JobContext` (T2.2) — `run(context)`. Extended by all 5 jobs.
- `MorningBriefingJob.__init__` (T2.3) takes `gmail`, `calendar`, `agent_loop`, `personality`, `name_for_briefing`.
- `EveningWrapJob.__init__` (T2.4) takes `gmail`, `agent_loop`, `personality`, `name_for_briefing`.
- `PreMeetingPrepJob.__init__` (T2.5) takes `calendar`, `agent_loop`, `personality`, `minutes_before`, `window_minutes`, `skip_titles`.
- `WeeklyReviewJob.__init__` (T2.6) takes `gmail`, `calendar`, `agent_loop`, `personality`, `name_for_briefing`.
- `FollowupReminderJob.__init__` (T2.7) takes `stakeholders`, `today`, `staleness_days`.
- `simulate` (T2.13) constructs all 5 jobs with the matching kwargs. ✓
- `Check` (T4.12) base + `CheckResult` — extended by 10 doctor checks (T4.12-T4.15).
- `InterviewMachine` (T4.9) — `start`, `next_question`, `answer`, `is_complete`, `current_step_index`, `resume`. Used by `interview_cmd` (T4.10).

**Drift risk:** Every task has the matching command registration in `cli/main.py`. The plan reminds the engineer to register each command in its task; if a task is skipped, the corresponding test will fail.

If any of the above don't hold when you re-read the plan, fix it inline.

---

## Future work (NOT in Plan 1)

- **Plan 2** — `rovik-keevs` migration: Phase 3 (build rovik-keevs), Phase 4 (parallel run), Phase 5 (cutover). Includes the `cosinabox migrate-from cos-agent` SQLite copier as a v0.1 deliverable in its own right.
- **Plan 3** — Public launch: Phase 6 of the spec. PyPI publish workflow, Docker registry publish workflow, Railway template, GitHub template repo, README, AGENTS.md, CONTRIBUTING.md, OUT_OF_SCOPE.md, LICENSE finalization, FUNDING.yml, SPONSORS.md, issue template, soft-launch announcement.

Both plans will be written in separate sessions after Plan 1 retro is complete.

