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
- `docs/agent/consult.md` — expose this CoS to external AI tools via MCP (optional, `[consult]` extra)

## See also

- `BEST_PRACTICES.md` — the wisdom file. Short. Read it.
- The engine docs: https://github.com/rovikrobert/cosinabox

## What's next

If you're a fresh agent session and the user says "set up my CoS", read `docs/agent/persona-interview.md` and start at step 1. Don't improvise — that file is the script.

If the user is an existing user and asks for a specific change, read the matching sub-doc and run the corresponding `cosinabox` CLI command.

If anything is unclear, ask the user before acting. Don't guess on a CoS — generic CoS is the failure mode.
