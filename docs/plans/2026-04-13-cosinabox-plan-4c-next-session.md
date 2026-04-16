# CoSinaBox Plan 4C — Next Session Kickoff

**Date:** 2026-04-13 (updated 2026-04-14: blockers cleared)
**Context:** Plan 4C (scheduling sub-system) — Tasks 1-3 done. Tasks 4-12 remaining.

**Status (2026-04-14):** PRs #11 (Plan 4A) and #14 (Plan 4B) are merged to main. plan4c-scheduling has been merged with new main (5 conflicts resolved, 340 tests passing) and pushed. Ready to execute Tasks 4-12.

## Session prompt

```
Continue cosinabox Plan 4C scheduling sub-system implementation. Tasks 1-3 are complete and committed on the plan4c-scheduling branch.

## What's done (Plan 4C Tasks 1-3)

Branch: ~/.worktrees/cantina/plan4c-scheduling (merged with main 2026-04-14, 340 tests pass)

- Task 1: Schema (5 scheduling tables in memory.db) + models (SchedulingStatus enum, Participant/TimeSlot/SchedulingRequest dataclasses) + sync DB layer (CRUD operations using Memory._conn)
- Task 2: Participant resolution (timezone + channel routing, no hardcoded mappings)
- Task 3: Slot scorer (6-dim weighted scoring + hard block + multi-timezone overlap)
- Stress test fixes: PRAGMA foreign_keys=ON, SchedulingStateError wrapping IntegrityError, OWNER_REVIEW renamed from ROVIK_REVIEW, 41 scheduling tests + 2 integrity tests

## What's remaining (Plan 4C Tasks 4-12)

Read the plan: docs/superpowers/plans/2026-04-13-cosinabox-plan-4c.md

- Task 4: Backchannel / move engine — priority classification + move proposals (port from cos-agent/src/scheduling/backchannel.py)
- Task 5: Response parser — Sonnet NL parser + callback data parser (cost-tracker wired)
- Task 6: Outreach — Telegram inline keyboard + Gmail draft (port from cos-agent/src/scheduling/outreach.py)
- Task 7: Coordinator — state machine with _TRANSITIONS dict, all 8x8 transition test coverage
- Task 8: Polling job — 30-min check, nudge at 24h, expire at 48h
- Task 9: Tool definitions — schedule_group_meeting, scheduling_status, scheduling_respond (built dynamically with owner_name)
- Task 10: Telegram callback handler — extends bot/telegram.py with register_callback_handler()
- Task 11: Wire into App.run() + OSS docs (scheduling.md with Phase B caveat)
- Task 12: Final validation + push + PR

## Blockers — RESOLVED (2026-04-14)

PRs #11 and #14 are merged. plan4c-scheduling is merged with new main and pushed. No rebase work needed — go straight to Task 4.

After Task 12 (Plan 4C PR merged), rovik-keevs needs to sync from new main:
```
cp -r ~/.worktrees/cantina/plan4c-scheduling/src/cosinabox/ /tmp/rovik-keevs/cosinabox/
```

## Important context

- Engine repo: ~/cosinabox (worktree for 4C: ~/.worktrees/cantina/plan4c-scheduling)
- rovik-keevs: /tmp/rovik-keevs (deployed on Railway, shadow mode)
- After engine PR #11 + #14 merged: cp -r ~/.worktrees/cantina/plan4c-scheduling/src/cosinabox/ /tmp/rovik-keevs/cosinabox/
- Test command: .venv/bin/pytest -q from worktree root
- Stakeholder-based extraction (Plan 4B) targets stakeholders with cadence daily/weekly only

## Implementation principles

- Port from cos-agent — battle-tested, don't rewrite
- Strip async throughout (cos-agent uses aiosqlite, cosinabox is sync)
- Replace hardcoded "Rovik" with owner_name parameter
- Replace hardcoded "claude-sonnet-4-5-20250514" with cosinabox.defaults.SONNET_MODEL_ID
- Replace hardcoded "SGT" with dynamic timezone display
- All Sonnet calls go through CostTracker.record() for cost tracking
- Test between each task — run .venv/bin/pytest -q before committing
- Stress test before shipping (use general-purpose subagent)

## OSS-friendly principles (mandatory)

The cosinabox engine is OSS. Every line of code, config, and doc will be read by someone who didn't write it. Adopt the perspective of a founder running cosinabox init for the first time:

1. No hardcoded names, orgs, or domains
2. Every capability must be discoverable via agent-facing docs
3. Show tradeoffs (what you gain enabling X vs what you lose)
4. Fallbacks must be explicit (log warnings when integrations missing)
5. Configuration happens through Claude Code conversation, not direct YAML editing
6. Defaults must be safe for strangers
7. Templates are first impressions — comment everything inline

These are codified in the engine's CLAUDE.md. Read it.
```

## Reference docs

- Spec: `docs/superpowers/specs/2026-04-13-cosinabox-plan-4c-design.md`
- Plan: `docs/superpowers/plans/2026-04-13-cosinabox-plan-4c.md`
- cos-agent source to port: `~/Cantina/cos-agent/src/scheduling/`
- Engine CLAUDE.md (OSS principles): `~/cosinabox/CLAUDE.md`

## Estimated effort

- PR conflict resolution: 1-2h (depends on conflict density)
- Tasks 4-12: ~12h sequential, faster with subagents
- Total next-session work: ~14h
