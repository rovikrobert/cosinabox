# CoSinaBox — Open-Source Chief of Staff Engine

**Spec date:** 2026-04-11
**Status:** Design approved, ready for implementation plan
**Author:** Rovik (with Claude)
**Target version:** v0.1.0 (alpha)

---

## 1. Vision & Positioning

**Project name:** `CoSinaBox` (brand) / `cosinabox` (repo, Python package, CLI command).

**One-liner:** *Open-source Chief of Staff in a box. Opinionated, proactive, runs on your own infra.*

**Positioning vs OpenClaw:** OpenClaw is a kit of parts — you assemble an assistant from 100 skills. CoSinaBox is a finished product with a job: it runs your day. It ships with default morning briefing, pre-meeting prep, evening wrap, weekly review, and follow-up tracking. Users configure *who it's for*, not *what it does*.

**Target user:** Technical founders, PMs, ops leads, EAs — people who use Claude Code (or Cursor / similar AI coding agents) and want a self-hosted Chief of Staff. Setup time target: ~30 minutes (honest about the OAuth wall).

**Privacy posture:**
- Strict zero telemetry by default.
- AGPL-3.0 license to protect against SaaS extraction without contribution.
- Runs entirely on user's infra with their API keys.
- README documents every external service the engine touches and what data flows where.

**Dogfooding requirement (hard rule):** Rovik runs his personal Keevs *against* the public `cosinabox` engine, not a private fork. The `rovik-keevs` repo becomes the canonical thin user repo. If this stops being possible, it's a critical bug in the engine.

**Monetization:** Path E — AGPL + GitHub Sponsors. No paid tiers, no premium features, no license keys. Sponsorship is gratitude, not a contract. Explicit non-promises in the README.

---

## 2. Architecture: Engine + Thin User Repo

**The pattern:** Hugo + content, or Next.js + app code. The engine is an installable Python package; users have a tiny repo that imports it and supplies config.

### Two repos

**`cosinabox/`** — public, AGPL, the engine.

```
cosinabox/
├── pyproject.toml                  # published to PyPI as `cosinabox`
├── LICENSE                         # AGPL-3.0
├── README.md
├── AGENTS.md                       # for agents browsing engine source
├── CONTRIBUTING.md
├── .github/
│   ├── FUNDING.yml                 # GitHub Sponsors link
│   └── workflows/                  # CI: tests, build, publish to PyPI on tag
├── src/cosinabox/
│   ├── __init__.py                 # exports App, Job, Tool, Personality
│   ├── app.py                      # main entry: App(config_dir).run()
│   ├── agent.py                    # Claude orchestration, tool loop
│   ├── bot/telegram.py             # Telegram adapter (only one in v0.1)
│   ├── memory/                     # SQLite layer
│   ├── scheduler/                  # APScheduler + built-in jobs
│   ├── jobs/                       # 5 core built-in jobs (see Section 3)
│   ├── tools/                      # built-in tool catalog
│   ├── prompts/                    # default prompt templates with {{personality}} slots
│   ├── personas/                   # one persona template (founder)
│   ├── interview/                  # state machine for cosinabox interview
│   ├── cli/                        # cosinabox init, doctor, simulate, etc.
│   ├── schemas/                    # JSON Schemas for all config files
│   └── defaults.py                 # all encoded operational defaults (see Layer 1)
├── templates/user-repo/            # scaffold copied by `cosinabox init`
└── tests/
```

**`rovik-keevs/`** — private, the user repo.

```
rovik-keevs/
├── pyproject.toml                  # depends on cosinabox==0.1.x
├── Dockerfile                      # FROM cosinabox/runtime:0.1.x
├── main.py                         # 3 lines: from cosinabox import App; App().run()
├── personality.md                  # voice + stakes (interview output)
├── stakeholders.yaml               # VIPs + cadence
├── jobs.yaml                       # which built-in jobs, when, with filters
├── integrations.yaml               # which tools to load
├── prompts/                        # optional prompt overrides
│   └── morning_briefing.md         # (optional) override for built-in
├── custom_jobs/                    # optional Python escape hatch
│   ├── competitive_intel.py        # (was Asia Lab Tracker)
│   ├── vip_relationship.py         # (was Rela)
│   ├── weekly_synthesis.py         # (was Mira)
│   └── attio_sync.py               # (was Attio CRM sync)
├── tests/                          # agent-generated tests for custom code
├── .env                            # secrets (gitignored, set in Railway)
├── .gitignore                      # strict; .env, *.db, __pycache__
├── CLAUDE.md                       # agent index → docs/agent/*
├── BEST_PRACTICES.md               # human + agent reference
├── docs/agent/
│   ├── safety.md                   # non-negotiable rules
│   ├── persona-interview.md        # 10-step setup script
│   ├── editing-config.md           # how to edit each file
│   ├── adding-custom-jobs.md       # test-first workflow
│   ├── oauth-walkthrough.md        # versioned, dated GCP walkthrough
│   └── proactive-suggestions.md    # what the agent should watch for
└── .cosinabox/
    ├── schemas/                    # JSON Schemas (read-only refs from engine; live validation uses installed engine)
    └── pre-commit                  # validate + secret scan hook
```

### How it runs

`App()` reads config from `./` by default (or `COSINABOX_CONFIG_DIR`), composes personality + stakeholders + jobs into the engine, and starts the Telegram bot + scheduler. The user repo is what gets deployed to Railway. The engine is just a pip dependency.

### Why this works on Railway

The deployed artifact is the *user's* repo. They own its filesystem. The engine is installed via `pip install cosinabox` (or via `FROM cosinabox/runtime:0.1.x` Docker base image). No "config dir mounted into a container" gymnastics.

### Versioning contract

The engine follows semver. v0.1 launches as **alpha** (0.x = anything can break). User repos pin a version (`cosinabox==0.1.4`). Schema files have `schema_version: 1` field; `cosinabox migrate` walks each file forward to the engine's current schema, printing diffs before applying.

### Custom jobs escape hatch

User repo's `custom_jobs/*.py` files are auto-discovered and registered. Lets advanced users add their own jobs without forking the engine. This is the "level 3 customization" door we leave open even though v0.1 customization is level 2 — costs almost nothing to support and prevents "I want a custom job" issues from blocking adoption. **Risk:** dynamic Python execution. Acceptable for self-hosted single-user instances; never build a marketplace around it.

### Docker base image

`cosinabox/runtime:0.1.x` is built and pushed to a container registry from CI on tag. User Dockerfiles inherit from it. Updates to the base image propagate to user repos via `docker pull`. Means users never touch local Python — they edit YAML/markdown and push to a Railway-connected GitHub repo.

---

## 3. Engine Scope for v0.1

### Built-in jobs (the 5 core)

| Job | Default schedule | What it does |
|---|---|---|
| `morning_briefing` | 8:00 daily | Calendar + email + priorities + follow-ups, persona-styled |
| `evening_wrap` | 18:00 daily | Sent mail recap + open commitments |
| `pre_meeting_prep` | every 15 min | Auto-detects meetings 25-35 min out, sends attendee context |
| `weekly_review` | Fri 16:00 | Week recap with calendar + email + relationships |
| `followup_reminder` | 9:30 daily | Stale follow-ups (>14 days) from stakeholder log |

Each job is enabled/disabled and re-timed via `jobs.yaml`. Each accepts a per-job filter config. Each handles "tool not configured" gracefully — skip the affected section, don't crash.

### Built-in tools

| Tool | Required for first run? | Install |
|---|---|---|
| `anthropic` | Yes | core dep |
| `telegram` | Yes | core dep |
| `gmail` + `calendar` | Yes (Google OAuth bundle) | `pip install cosinabox[google]` |
| `fireflies` | No (opt-in) | `pip install cosinabox[fireflies]` |
| `web_search` (Serper) | No (opt-in) | `pip install cosinabox[search]` |

**Optional dependency groups** keep the install lean. Anthropic-only users can skip everything else.

### Persona templates

**One template (`founder`)** ships in v0.1. It's the closest match to Rovik's dogfood case and the most generally useful starting point. Additional personas (PM, ops, EM, EA) come from community contributions or v0.2.

### Built-in features (always on)

- Conversation summarization (>25 message threshold)
- Calendar conflict detection on event creation
- Cost tracking + per-message cap + daily budget enforcement
- Prompt-injection defense on tool results
- Scheduled-job session isolation
- Model routing (Sonnet default, Opus on strategic prompts)
- Graceful degradation when an integration is missing

### Layer 1 — encoded operational defaults

These ship as defaults in `cosinabox/defaults.py`, each with a comment explaining the reasoning and the date the value was chosen:

| Lesson | Default |
|---|---|
| Cost runaways are real | Per-message cap $0.75, daily cap $15 |
| Tool loops can blow up | `MAX_TOOL_ITERATIONS = 8` |
| Long contexts degrade quality and burn money | Conversation summarization at >25 messages |
| Anthropic rate limits hit on heavy jobs | 2s delay between tool iterations |
| Calendar double-booking is silent and painful | Conflict detection on every event creation |
| Briefings shouldn't load conversation history | Scheduled jobs use isolated session contexts |
| Opus is for strategy, not chitchat | Sonnet default; Opus only on strategic-keyword prompts |
| Group chats expose too much surface | Group mode restricted to calendar + web search |
| Stale data accumulates | Auto-cleanup of >30-day-old conversations |
| Tool results need prompt-injection defense | Untrusted-data wrapping on all external tool output |
| Pre-meeting prep needs a window | 25-35 min before event, configurable |
| Follow-up staleness is real | Default threshold = 14 days |
| API errors confuse users | Targeted error messages (credits, rate limit, overloaded, auth) |

### Deferred to v0.2+

post_meeting_debrief, commitment_check, vip_relationship_scan, vip_relationship_audit, weekly_synthesis, competitive_intel, Slack, Attio, Drive, additional persona templates, multi-channel adapters, CRM adapter abstraction, plugin marketplace, web UI, multi-tenant mode.

---

## 4. User Config Schema

The user-editable surface area for v0.1 is small: 4 config files plus optional overrides plus `.env`. Every file has a `schema_version` field at the top and a JSON Schema sibling for agent-validated edits.

### `personality.md`

Markdown, free-form. Loaded into the system prompt. Persona templates seed this. Format:

```markdown
---
schema_version: 1
name: Alex
role: Founder of Loop AI
timezone: America/Los_Angeles
---

# Voice
You are my Chief of Staff. Be direct. Skip the throat-clearing.
Cut anything that isn't load-bearing.

# Stakes
We're 6 weeks from a Series A close. Every conversation is either
moving us toward signed term sheets or it isn't.

# Defaults
- Default to bullets, not paragraphs
- Surface conflicts before I ask
- If you're confident, act; if not, ask one tight question
```

### `stakeholders.yaml`

VIPs, relationships, cadence. Used by `morning_briefing`, `followup_reminder`, `weekly_review`.

```yaml
schema_version: 1
stakeholders:
  - name: Sarah Chen
    role: Lead investor (Sequoia)
    cadence: weekly
    last_contact: 2026-04-08
    notes: Wants monthly metric updates. Replies fastest in mornings.
  - name: David Park
    role: Co-founder
    cadence: daily
    notes: Don't surface 1:1s — we sync constantly.
```

### `jobs.yaml`

Which built-in jobs to enable, when, with what filter.

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
    enabled: false  # turn on after 2 weeks of usage
```

### `integrations.yaml`

Which tools to load + per-tool config (no secrets here, those go in env vars).

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

### `.env`

Secrets only, gitignored, deployed via Railway env vars.

```bash
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REFRESH_TOKEN=...   # produced by `cosinabox auth google`
```

### Optional: `prompts/<job_name>.md`

Drop a markdown file named after a built-in prompt to override its template. Engine falls back to default if absent.

### Optional: `custom_jobs/*.py`

Escape hatch for users who want to define their own jobs. Auto-discovered at startup. Documented as "advanced, here be dragons."

### JSON Schemas

Live in the engine package at `cosinabox/schemas/*.schema.json`. Used by `cosinabox validate` (always loaded from the installed engine, not from disk copies in the user repo). The user repo's `.cosinabox/schemas/` directory contains read-only reference copies for IDE/editor autocompletion only.

---

## 5. The Guided Agent-Led Setup (the heart of the system)

CoSinaBox is positioned as a **Claude-Code-first template**. The setup experience is not a CLI wizard or a README walkthrough — it's a structured interview that Claude Code (or Cursor / Aider / similar) runs by reading `CLAUDE.md`.

### Step 0 — User runs one command

```bash
pip install cosinabox
cosinabox init my-cos
cd my-cos
```

`cosinabox init` clones the user-repo template, drops the CLAUDE.md and sub-docs, scaffolds the empty config files, and prints:

> "Your CoSinaBox skeleton is ready in ./my-cos.
> Open this directory in Claude Code (or Cursor) and say 'set up my CoS.'
> Claude Code will read CLAUDE.md and walk you through the rest."

(v0.1 requires Python on the user's machine for `pip install`. The `npx cosinabox init` Node wrapper is deferred to v0.2.)

### Layer 3 — The interview state machine

### Step 1 — Agent runs the interview state machine

The interview is a **state machine owned by the engine**, not a script the agent improvises. The agent invokes `cosinabox interview` as a sub-program; the engine asks one question, the agent relays the answer back, the engine advances state and prompts the next question. This sidesteps the "agent batches questions" failure mode entirely.

The 10-step interview:

1. **Identity** — name, role, company, timezone. Goes into `personality.md` frontmatter.
2. **Stakes** — *"What's the most important thing happening in your work over the next 6 weeks?"* Becomes the first paragraph of personality.md "Stakes" section. **A CoS without stakes is a chatbot.**
3. **Voice** — *"Pick one: blunt / warm / analytical / formal / playful. Pick a runner-up. What's a phrase a great chief of staff has said to you that you wish you heard more often?"*
4. **Top stakeholders** — *"Name your 5 most important people right now. For each: role, cadence, anything I should know."* Builds initial `stakeholders.yaml`. **Start with 5, not 50.**
5. **Calendar reality** — *"Are you back-to-back? What should pre-meeting prep skip (lunch, focus blocks, internal 1:1s)?"* Tunes `pre_meeting_prep` filters. **Unfiltered prep on every meeting becomes noise.**
6. **Job staging** — *"For week 1, I'm enabling only `morning_briefing` and `pre_meeting_prep`. Sound good?"* **Stage the rollout.**
7. **API keys + OAuth** — agent walks the user through Telegram BotFather + Anthropic + Google OAuth as a literal step-by-step script from `docs/agent/oauth-walkthrough.md`.
8. **Budget caps** — *"Default daily cap is $15. Want to change?"* **Set caps before going live.**
9. **First simulation** — agent runs `cosinabox simulate morning_briefing --fixture=sample` and shows the output. **See it before you ship it.**
10. **Deploy** — agent walks through Railway template button + GitHub repo connect + env var entry.

Each step is opinionated. The agent pushes back when the user's answer would lead to a bad CoS, with a one-line explanation of the lesson. Every opinion is a recommendation, not a block — the user retains override authority.

### Step 2 — Agent writes config as it goes

After each interview step, the agent runs the corresponding `cosinabox` CLI command (or edits the YAML directly if no command exists yet). After every edit, it runs `cosinabox validate` and `cosinabox describe`, then shows the user a 3-line summary: *"Added Sarah Chen as a weekly-cadence stakeholder. You now have 5 stakeholders tracked. Looks right?"*

### Step 3 — OAuth wall handholding

Google OAuth requires manual clicks in the GCP console. The agent reads `docs/agent/oauth-walkthrough.md` and reads the steps to the user *one at a time*, waiting for confirmation between each. The walkthrough is versioned and explicitly dated (*"Last validated against Google Cloud console UI on YYYY-MM-DD"*). When the GCP UI changes, the doc gets updated and re-shipped via `cosinabox upgrade-docs`.

### Step 4 — First simulation, before deploying

```bash
cosinabox simulate morning_briefing --fixture=sample
```

Runs the morning briefing locally against a curated `sample` fixture (8 plausible calendar events, 12 plausible emails, 5 plausible stakeholders — designed to exercise every feature of `morning_briefing`). Prints what would have been sent to Telegram. Agent shows the output and asks: *"This is roughly what your morning briefing will look like tomorrow. Want to tweak?"*

If the user wants tweaks, the agent edits `personality.md` or `prompts/morning_briefing.md` and re-runs simulate. Loop until the user says "ship it." **Dry-run before deploy beats guess-and-pray.**

### Step 5 — Deploy

Agent walks the user through:
1. Push the user repo to GitHub (private repo).
2. Click the Railway template button (URL prefilled with the GitHub repo).
3. Railway prompts for env vars — agent dictates each one.
4. Railway deploys.
5. Agent runs `cosinabox doctor --json` against the deployed instance and parses the result.
6. If green, agent says: *"You're live. Tomorrow at 8am you'll get your first morning briefing in Telegram. I'll check on you in a week."*
7. Bot self-schedules a `check_in_followup` job that fires a Telegram message on day 7 prompting the user to come back for tuning.

### Step 6 — Day 7 check-in

When the user returns and says "check on my CoS," the agent runs `cosinabox doctor` and walks through:
- Did briefings actually arrive each morning?
- How many followups were missed? (Suggest enabling `followup_reminder` if stakeholder log has data.)
- Are pre-meeting preps firing on the right meetings? (Suggest filter tweaks if noise.)
- Is cost in line? (Suggest budget review if hot.)
- Does the personality feel right? (Offer to revise based on a week of real output.)

This is the layer-2 "proactive suggestions" rules in action.

### Layer 2 — CLAUDE.md guardrails

The `CLAUDE.md` shipped in the user repo template is a top-level **index** that points to smaller files in `docs/agent/`. Each sub-file is loaded by the agent only when relevant, keeping individual files small enough to fit fully into agent context.

**Safety rules (non-negotiable, in `docs/agent/safety.md`):**
- API keys live ONLY in `.env`. Never write them to tracked files. Pre-commit hook will block.
- Always run `cosinabox validate` before committing config edits.
- Always run `cosinabox simulate <job>` after editing a job's config or prompt.
- Never edit files in `.cosinabox/` (engine internals).
- Never `git push --force`. Never bypass pre-commit hooks.
- Deploy via PR merge only, never direct push to main.
- Never write to API keys anywhere except `.env`.

**Quality rules (in `docs/agent/editing-config.md`):**
- Prefer **config edits** > **prompt overrides** > **custom Python code**, in that order.
- When adding a stakeholder, always ask: name, role, cadence, notes. Don't leave fields blank.
- When editing `personality.md`, run the persona interview. Never write a generic personality from a one-line user request.
- When enabling a new job, recommend simulate-mode for 2-3 days before deploying.
- After any edit, run `cosinabox describe` and show the user the English diff.

**Workflow rules (in `docs/agent/adding-custom-jobs.md`):**
- New custom job? **Test-first.** Write a fixture + a `test_<job>.py` before the job logic.
- After deploying, run `cosinabox doctor --json` and parse the result.
- Run `cosinabox describe` before and after multi-file edits.

**Proactive suggestions (in `docs/agent/proactive-suggestions.md`):**
- If user has been running >2 weeks and `followup_reminder` is disabled, suggest enabling it.
- If user mentions a missed meeting, check if `pre_meeting_prep` is enabled and tuned.
- If user complains the briefing is wrong, recommend prompt overrides over personality.md edits (more surgical).

### Layer 4 — `cosinabox doctor` checks

Not just connectivity. Checks for the things Keevs has gotten wrong:

| Check | Triggered when | Why |
|---|---|---|
| `personality_thin` | personality.md is <500 chars or matches template | Generic personality = generic briefings |
| `stakeholders_empty` | stakeholders.yaml has <3 entries after 7 days | Followup_reminder won't work without data |
| `cost_runaway` | daily spend >80% of cap on any day in last week | User should review tool usage or raise cap |
| `tool_loop_excess` | avg tool iterations per message >6 | Prompts may be too vague, agent is thrashing |
| `prep_noise` | pre_meeting_prep firing >8x per day | Filter rules need tuning |
| `briefing_drift` | morning_briefing prompt overridden but not validated in simulate | User edited and didn't test |
| `secret_in_tracked_file` | any tracked file matches known key prefix | Secret leak — block immediately |
| `stale_followups` | >20 stakeholders past their cadence | User isn't acting on the briefing — surface differently |
| `oauth_expiring` | Google OAuth refresh token expires in <14 days | Re-auth before it breaks |
| `schema_outdated` | any config file uses schema_version older than engine | Suggest `cosinabox migrate` |

`cosinabox doctor --json` outputs all checks as parseable. The agent reads the result and surfaces issues to the user proactively.

### Layer 5 — `BEST_PRACTICES.md`

Shipped in the user repo template. Short, opinionated, written for humans (and read by agents). The "wisdom" file. Sections:

- **Start small.** Two jobs, five stakeholders. Add more after a week of dogfooding.
- **Tune after, not before.** Don't perfect personality.md on day one.
- **The morning briefing is a contract.** If you stop reading it, the bot has failed.
- **Stakeholder cadence is honest, not aspirational.** If you can't actually contact someone weekly, set monthly.
- **Custom jobs are a last resort.** 90% of "I want a custom thing" is "I want to override a prompt."
- **Cost caps are a forcing function, not a budget.** Hit the cap = your prompts are too greedy.
- **Trust the doctor.** When `cosinabox doctor` flags something, fix it that week.

### CLI commands (agent-friendly)

All commands support `--json` output. All idempotent. All intent-based:

```bash
cosinabox init <dir>                                  # scaffold user repo
cosinabox interview                                   # run setup state machine
cosinabox add-stakeholder --name --role --cadence
cosinabox set-job-schedule <job> --cron
cosinabox enable-job <job>
cosinabox disable-job <job>
cosinabox set-persona --role founder
cosinabox simulate <job> [--fixture=sample]           # local dry-run
cosinabox validate                                    # schema-check all config
cosinabox doctor [--json]                             # health checks
cosinabox describe                                    # English summary of config
cosinabox migrate                                     # bump schema versions
cosinabox upgrade-docs                                # re-sync docs/agent/* templates
cosinabox auth google                                 # OAuth refresh-token flow
cosinabox test                                        # wraps pytest with right env
```

### Pre-commit hook

Ships in user repo template. Runs `cosinabox validate` + secret-scanning (matches known key prefixes like `sk-ant-`, `xoxb-`, `AIza`, etc.) and blocks the commit if either fails.

---

## 6. Migration Path for Current cos-agent

The migration is the proof. If Rovik can't migrate his own running bot to the new architecture without losing functionality, the architecture is wrong.

### Phase 0 — Snapshot

Tag current `cos-agent` master as `pre-cosinabox-migration`. Clean rollback point.

### Phase 1 — Engine extraction (week 1)

In the new public repo `cosinabox`, copy the *generic* parts of `cos-agent`:

| From cos-agent | To cosinabox engine | Notes |
|---|---|---|
| `src/agent.py` | `cosinabox/agent.py` | Strip Rovik-specific routing rules; keep generic loop |
| `src/bot.py` | `cosinabox/bot/telegram.py` | Strip dual-account assumptions; keep DM/group split |
| `src/memory.py` | `cosinabox/memory/sqlite.py` | Schema unchanged, code generic |
| `src/router.py` | `cosinabox/agent/routing.py` | Default rules; user can override |
| `src/cost_tracker.py` | `cosinabox/agent/cost.py` | Defaults from Layer 1 |
| `src/scheduler.py` + `briefing_pipeline.py` | `cosinabox/scheduler/` | Only the 5 core jobs |
| `src/prompts/core.py` + `briefing.py` | `cosinabox/prompts/` | With `{{personality}}` slots replacing hardcoded names |
| `src/tools/google_auth.py`, `gmail_tool.py`, `calendar_tool.py` | `cosinabox/tools/google/` | Single-account by default |
| `src/tools/fireflies_tool.py` | `cosinabox/tools/fireflies.py` | Optional dependency |
| `src/tools/web_search_tool.py` | `cosinabox/tools/web_search.py` | Optional dependency |
| `tests/` | `cosinabox/tests/` | Carry over; rewrite to use generic fixtures |

For every file copied, ask: *"Would I include this if I were starting fresh?"* If no, it goes to `rovik-keevs/custom_jobs/` instead.

### Phase 2 — Engine first-run (week 1-2)

Get `cosinabox` to a state where a fresh user repo with sample fixture data can:
- Validate config
- Run `simulate morning_briefing` and produce reasonable output
- Pass its own pytest suite

Milestone: "engine alone works." No Rovik-specific config touched yet.

### Phase 3 — Build `rovik-keevs` (week 2)

Create the new private repo `rovik-keevs` as a thin user repo. Copy Rovik's personal content out of `cos-agent`:

| From cos-agent (private/personal) | To rovik-keevs |
|---|---|
| `SOUL.md` | `personality.md` (with frontmatter added) |
| Hardcoded stakeholder logic in prompts | `stakeholders.yaml` |
| Hardcoded scheduled jobs config | `jobs.yaml` |
| Hardcoded prompt overrides for Rovik's voice | `prompts/morning_briefing.md`, etc. |
| Asia Lab Tracker | `custom_jobs/competitive_intel.py` |
| Rela | `custom_jobs/vip_relationship.py` |
| Mira | `custom_jobs/weekly_synthesis.py` |
| Dual Google account OAuth | `integrations.yaml` advanced + `.env` extras |
| Attio sync | `custom_jobs/attio_sync.py` |
| Cantina relevance filtering | per-job `filter:` in `jobs.yaml` |

Each `custom_jobs/*.py` file validates that the escape hatch works.

### Phase 4 — Parallel run (week 2-3)

For ~5 days, run BOTH `cos-agent` and `rovik-keevs` on Railway simultaneously:
- Old bot sends to user's primary Telegram chat (unchanged behavior).
- New bot sends to a separate "shadow" chat that only Rovik watches.
- New bot runs in **read-only mode for any tool that mutates external state** — no calendar event creation, no Attio writes, no email sends. Reads and analyses only.

Compare output every day:
- Are morning briefings equivalent?
- Equivalent pre-meeting prep?
- Equivalent costs?
- Any features that feel worse?

Anything worse in `rovik-keevs` is a bug in the engine or in personal content migration. Fix and re-deploy.

### Phase 5 — Cutover (end of week 3)

Once parallel run shows parity (or better):
1. Stop the old `cos-agent` Railway service (don't delete — keep cold standby for 30 days).
2. Switch Telegram bot token to point at `rovik-keevs`.
3. Archive `cos-agent` repo (read-only, kept for history).
4. `rovik-keevs` becomes the only running CoS.

### Phase 6 — Public launch (week 3-4)

With `rovik-keevs` running on top of public `cosinabox`, dogfooding is proven. Make `cosinabox` public:
1. Final license check (AGPL).
2. Final secret scan on the engine repo.
3. README + AGENTS.md polish.
4. Tag `v0.1.0`.
5. Push to GitHub public.
6. Soft-launch announcement (one tweet, optional HN post). Frame as "0.x alpha — for people who want to build on it now."

### `cosinabox migrate-from cos-agent`

A v0.1 deliverable in its own right. CLI command that copies relevant tables from the old `cos.db` SQLite into the new `rovik-keevs/data/` SQLite, mapping schema where needed. Without this, parallel run is meaningless (the new bot would have no follow-up history, no stakeholder log, no conversation summaries).

### Realistic timeline

3 weeks at full focus, 4-6 weeks at part-time pace given Cantina day-job obligations. Explicit checkpoint at end of week 2 — if engine extraction isn't done, push public launch to week 5+. Don't compress.

---

## 7. License, Distribution, Branding

### License: AGPL-3.0

- AGPL forces hosted-service forks to publish modifications under the same license.
- Companies can still use CoSinaBox internally without restrictions.
- AGPL friction filters in the right direction (audience is individual operators, not enterprises).
- File: `LICENSE` — standard AGPL-3.0 text. Optional `NOTICE` file for explicit copyright claim.

### Distribution channels

**Engine:**
- **GitHub:** `cosinabox/cosinabox` (new org under Rovik's personal account, not Cantina). Public, AGPL.
- **PyPI:** `cosinabox` package, published from CI on tag. v0.1.x at launch.
- **Docker registry (Docker Hub or GHCR):** `cosinabox/runtime:0.1.x` base image. Built and pushed from CI on tag.
- **Railway template:** one-click deploy template pointing at the user-repo scaffold, with env-var prompts pre-filled.

**User repo template:**
- Lives in `cosinabox/templates/user-repo/` inside the engine repo.
- Scaffolded by `cosinabox init`.
- Also published as a standalone GitHub template repo (`cosinabox/template-user-repo`) for "Use this template" via GitHub UI.

**Documentation:**
- **README.md** — humans visiting GitHub. 1-page positioning, link to setup, link to AGENTS.md, link to BEST_PRACTICES.md.
- **AGENTS.md** in the engine repo — for agents browsing engine source (Claude Code making engine PRs).
- **CONTRIBUTING.md** — 0.x = anything can break, PR conventions, test running, code of conduct.
- Docs site (mkdocs / Mintlify) deferred to v0.2.

### Branding

- **Project name:** `CoSinaBox` (brand) / `cosinabox` (technical).
- **Tagline:** "Open-source Chief of Staff in a box. Opinionated, proactive, runs on your own infra."
- **Logo:** deferred to v0.2.
- **Domain:** `cosinabox.dev` if available; check before committing. Falls back to GitHub-only for v0.1.
- **GitHub org:** `cosinabox`, owned by Rovik's personal account (not Cantina IP).
- **No social presence at v0.1.** Easier to start a community late than abandon one.

### Sponsorship layer (Path E)

- **`.github/FUNDING.yml`** — points GitHub's "Sponsor" button at Rovik's GitHub Sponsors profile. Requires enabling GitHub Sponsors first (~10 min, has approval process).
- **Optional fallback:** Polar.sh / Open Collective / Buy Me a Coffee links alongside GitHub Sponsors for users who avoid GitHub for billing.
- **README "Sponsoring" section** — friendly, brief, near the bottom. Sample copy (the `(link)` placeholder gets replaced with the real GitHub Sponsors URL when the file is written):
  > *CoSinaBox is built and maintained by Rovik in spare time. If it saves you time, [GitHub Sponsors](link) is the easiest way to chip in. There are no sponsor-only features and no tiers — sponsoring is purely a thank-you, and the gratitude makes the maintenance feel less lonely.*
- **`SPONSORS.md`** — public thanks list, hand-maintained or auto-updated from the GitHub Sponsors API.
- **Explicit non-promises in the README:**
  > *Sponsoring does not entitle you to support, priority issues, or features. CoSinaBox is open source and AGPL. Sponsorship is gratitude, not a contract.*

### Soft-launch posture

- No marketing budget, no PR push. Soft-launch with one tweet + optional HN post.
- AGPL + 30-min setup + Claude Code requirement naturally filters for serious adopters.
- Set explicit expectations: "Maintained by one person in spare time. Issues triaged weekly. PRs welcome but reviewed slowly. 0.x means anything can change."
- README "What this isn't" section: not a chatbot, not a multi-tenant SaaS, not a no-code tool, not a replacement for OpenClaw if you want a kit of parts.
- Issue template filters for "have you read CLAUDE.md / BEST_PRACTICES.md / run `cosinabox doctor`?" before allowing issue creation.

---

## 8. Out of Scope for v0.1

Explicit non-features. Point at this section when scope creep tries to sneak in.

### Deferred to v0.2 or later

- Multi-channel adapters (WhatsApp, Slack outbound, Discord, iMessage, Signal)
- Channel abstraction interface (YAGNI until there's a second channel)
- Plugin marketplace / shared `custom_jobs` registry
- Web UI for configuration (Claude Code is the UI)
- Multi-tenant or multi-user mode
- Voice synthesis or outbound voice
- Attio CRM integration (lives in `rovik-keevs/custom_jobs/` for v0.1)
- Slack integration (entirely)
- Drive integration (entirely)
- Generalized VIP relationship tracker (was Rela)
- Generalized weekly synthesis (was Mira)
- Competitive intel tracker (was Asia Lab Tracker) — v0.2 launch feature
- Additional persona templates beyond `founder`
- Localization (English-only at v0.1)
- Web dashboard / observability UI
- Opt-in telemetry (strict zero in v0.1)
- `npx cosinabox init` Node wrapper
- Docs site (markdown in repo only at v0.1)
- CRM adapter interface (designed against two implementations, not one)
- Custom prompt templates beyond the 5 core jobs
- Logo and visual branding
- Sponsor tiers, premium features, license keys, paid Discord, priority support — **explicitly never, per Path E**

### Things explicitly never in scope (the "this isn't OpenClaw" list)

- General-purpose tool wiring (not a kit-of-parts framework)
- Code execution / shell access tools
- Browser automation
- File system tools
- Remote desktop / GUI automation
- Anything that turns CoSinaBox into a general-purpose AI agent platform

CoSinaBox is opinionated about being a Chief of Staff. If a feature would make sense in OpenClaw but not specifically for a CoS, it doesn't belong here.

The "never" list lives in `OUT_OF_SCOPE.md` and is not in stone. If priorities change, update the file with the reason. The point is to be explicit *now*, not bind a future self.

---

## v0.1 Deliverables Summary

A consolidated checklist of what ships in v0.1.0. **Note for the implementation plan:** this list is too large for a single execution chunk — the plan should decompose it into 6 milestones, each independently shippable and testable: (1) engine extraction from cos-agent, (2) engine first-run with sample fixture, (3) user repo template + CLAUDE.md + sub-docs, (4) CLI commands + interview state machine + doctor checks, (5) `rovik-keevs` migration + parallel run, (6) public launch (PyPI + Docker registry + GitHub public + announcement). Each milestone has a clear "done" criterion and a rollback path.

### Engine package (`cosinabox` on PyPI)

- [ ] Core: agent loop, model routing, cost tracking, conversation summarization, prompt-injection defense
- [ ] Telegram bot adapter (DM + group modes, voice, photo, PDF)
- [ ] SQLite memory layer
- [ ] APScheduler integration
- [ ] 5 built-in jobs: morning_briefing, evening_wrap, pre_meeting_prep, weekly_review, followup_reminder
- [ ] Built-in tools: anthropic, telegram, gmail, calendar, fireflies (opt), web_search (opt)
- [ ] Optional dependency groups: `[google]`, `[fireflies]`, `[search]`
- [ ] One persona template: `founder`
- [ ] Prompt templates with `{{personality}}` slots
- [ ] JSON Schemas for all 4 user config files
- [ ] Encoded operational defaults in `defaults.py` (all Layer 1 lessons)
- [ ] Engine test suite (port + adapt from cos-agent's tests)

### CLI

- [ ] `cosinabox init <dir>`
- [ ] `cosinabox interview` (state machine)
- [ ] `cosinabox add-stakeholder` / `set-job-schedule` / `enable-job` / `disable-job` / `set-persona`
- [ ] `cosinabox simulate <job> [--fixture=sample]`
- [ ] `cosinabox validate`
- [ ] `cosinabox doctor [--json]` with all 10 checks from Section 5
- [ ] `cosinabox describe`
- [ ] `cosinabox migrate`
- [ ] `cosinabox upgrade-docs`
- [ ] `cosinabox auth google`
- [ ] `cosinabox test`
- [ ] `cosinabox migrate-from cos-agent --db <path>` (one-shot migration tool)
- [ ] `--json` output mode on every read-oriented command

### User repo template

- [ ] `pyproject.toml` (depends on cosinabox)
- [ ] `Dockerfile` inheriting from `cosinabox/runtime`
- [ ] `main.py` (3-line entry point)
- [ ] Empty `personality.md` with frontmatter scaffold
- [ ] Empty `stakeholders.yaml` / `jobs.yaml` / `integrations.yaml` (with schema_version)
- [ ] `CLAUDE.md` (top-level index)
- [ ] `docs/agent/safety.md`
- [ ] `docs/agent/persona-interview.md`
- [ ] `docs/agent/editing-config.md`
- [ ] `docs/agent/adding-custom-jobs.md`
- [ ] `docs/agent/oauth-walkthrough.md` (versioned + dated)
- [ ] `docs/agent/proactive-suggestions.md`
- [ ] `BEST_PRACTICES.md`
- [ ] `.gitignore` (strict)
- [ ] `.cosinabox/pre-commit` hook (validate + secret scan)
- [ ] `.cosinabox/schemas/` read-only schema reference copies

### Distribution

- [ ] PyPI publish workflow (CI on tag)
- [ ] Docker registry publish workflow (CI on tag) — `cosinabox/runtime:0.1.x`
- [ ] Railway template (one-click deploy) pointing at user repo scaffold
- [ ] GitHub template repo `cosinabox/template-user-repo`

### Documentation

- [ ] `README.md` (engine repo): positioning, setup, links
- [ ] `AGENTS.md` (engine repo): for agents working on engine source
- [ ] `CONTRIBUTING.md`
- [ ] `OUT_OF_SCOPE.md`
- [ ] `LICENSE` (AGPL-3.0)
- [ ] `.github/FUNDING.yml`
- [ ] Issue template that filters for "have you read CLAUDE.md / run doctor?"
- [ ] `SPONSORS.md`

### Migration deliverables (rovik-keevs side)

- [ ] `rovik-keevs` private repo created
- [ ] Personal content extracted from `cos-agent` into `rovik-keevs`
- [ ] All deferred features (Asia Lab Tracker, Rela, Mira, Attio) implemented as `custom_jobs/*.py`
- [ ] `cosinabox migrate-from cos-agent` run to copy SQLite history
- [ ] Parallel run completed (5 days, shadow chat, read-only for mutations)
- [ ] Cutover to `rovik-keevs` as the only running CoS
- [ ] `cos-agent` archived

### Curated assets

- [ ] `sample` fixture (8 calendar events, 12 emails, 5 stakeholders) — designed to exercise every morning_briefing feature
- [ ] OAuth walkthrough doc validated against current GCP UI

---

## Key Tradeoffs & Risks

| Risk | Mitigation |
|---|---|
| Maintainer doesn't dogfood public engine | **Hard rule:** rovik-keevs runs against public cosinabox. Phase 4-5 of migration enforces this. |
| OAuth wall makes setup feel rough | Honest 30-min target in README + handheld walkthrough script the agent reads aloud. |
| Encoded lessons calcify as the world changes | Defaults live in single `defaults.py` with dated comments. Easy to revisit annually. |
| Schema changes break user repos | 0.x alpha contract + `cosinabox migrate` CLI + schema_version field on every config file. |
| Custom jobs escape hatch is a security risk | Document loudly. Never build a marketplace. Single-user self-hosted only. |
| `CLAUDE.md` becomes too large for agents to load | Split into sub-files in `docs/agent/`; CLAUDE.md is just an index. |
| Migration takes longer than 3 weeks | Explicit week-2 checkpoint; push public launch if engine extraction isn't done. |
| `migrate-from cos-agent` is harder than expected | Treat as v0.1 deliverable in its own right; spec table-by-table mapping. |
| Maintainer burnout from support load | Path E + non-promises + issue template + AGPL filter all reduce support burden. |

---

## What success looks like (for v0.1)

- `cosinabox` v0.1.0 published to PyPI
- `cosinabox/runtime:0.1.0` published to a Docker registry
- `rovik-keevs` running in production on top of public `cosinabox`
- `cos-agent` archived
- Public GitHub repo with README, LICENSE, FUNDING.yml, AGENTS.md
- 5-10 serious early adopters running their own CoSinaBox instances
- One soft-launch announcement made
- Zero regressions in Rovik's daily CoS experience (the briefings he gets each morning are at least as good as what `cos-agent` was producing)

What success does NOT look like (v0.1):
- High GitHub star count
- Lots of contributors
- Significant sponsorship revenue
- Press coverage
- Enterprise interest

These are v0.2+ aspirations if v0.1 finds product-market fit, not v0.1 deliverables.
