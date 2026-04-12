# CoSinaBox & Cantina Development Discipline

**Status:** Active commitments. Adopted 2026-04-11.
**Scope:** All work on `cosinabox` (the engine, when it exists), `rovik-keevs` (the personal user repo, when it exists), and ongoing Cantina engineering sessions where discipline failures matter.

## Why this exists

The CoSinaBox project is unusually well-suited as a forcing function for discipline because:

- **It's long-arc.** Weeks of work, many sessions, drift compounds.
- **It's meta.** The project itself encodes operational lessons. The discipline of building it should match the discipline it teaches its users.
- **It's public.** The engine repo will be visible. Discipline failures (broken CI, half-merged PRs, stale plans) are publicly visible failures.
- **It has natural milestones.** Six of them. Each is a checkpoint where we retro, adjust, and re-commit.

This document captures concrete discipline commitments with **enforcement mechanisms** wherever possible. A commitment without an enforcement mechanism is a wish.

The trigger for this doc was a real failure: the 2026-04-11 brainstorming/spec/plan session ran for hours without entering a worktree, despite "enter a worktree at session start" being the user's #1 rule. Rules in memory weren't enough. The discipline gap is real, and the answer is enforcement, not more reminders.

---

## The 8 commitments

Each commitment has four parts: **Rule** (what), **Why** (the reason — usually a past failure or named risk), **How to apply** (when it kicks in), and **Enforcement** (the mechanism that catches violations).

---

### 1. Worktree at session start

**Rule:** Every Claude Code session that touches files (code OR docs) MUST be running inside a git worktree before any file edit, no exceptions. The worktree path is `~/.worktrees/cantina/<branch-name>` (or for cosinabox once it exists, `~/.worktrees/cosinabox/<branch-name>`).

**Why:** Multiple concurrent Claude Code sessions can share a checkout. Without a worktree, one session's branch checkout moves HEAD for all sessions, causing lost work, merge conflicts, and the "linter removed my code" loop. Even when only one session is active, the discipline of always-worktree prevents the *next* concurrent session from causing a problem. Past failure: 2026-04-11 session ran for 4 hours on `main` directly because the rule was in memory but not enforced.

**How to apply:** At session start, before the first file edit, check `pwd`. If not under `~/.worktrees/`, create a worktree (`git worktree add ~/.worktrees/cantina/<branch> -b <branch>`) and `cd` into it. For subagents, pass the absolute worktree path explicitly (subagents have a known bug of guessing wrong paths — see `feedback_worktree_path.md`).

**Enforcement:**
- **Cantina `.claude/settings.json` SessionStart hook** prints a loud warning at session start if `pwd` doesn't match `~/.worktrees/cantina/...`. Hook script: `.claude/hooks/session-start-worktree-check.sh`.
- **UserPromptSubmit hook** (optional, more aggressive) prepends a reminder to every prompt if still on `main`. Skipping the worktree becomes friction-bearing instead of friction-free.
- For cosinabox once it exists, a parallel hook lives in `cosinabox/.claude/settings.json`.

---

### 2. The plan is the source of truth, not the chat

**Rule:** During execution of a written plan, future Claude Code sessions read the plan (and its checked/unchecked boxes) as the authoritative source of what's done and what's next. They do not read prior conversation transcripts. The plan must be self-contained enough that a fresh session with no memory and no chat history can pick up the next unchecked task and execute it correctly.

**Why:** Long projects span many sessions. Conversation context evaporates. Memory captures lessons but not progress. A plan that depends on chat history to be intelligible is a plan that gets dropped. Past failure pattern: "where were we?" sessions that re-do work or skip critical steps.

**How to apply:** When writing plans (writing-plans skill), test by asking: "Could a stranger with this plan and zero chat context do the next task correctly?" If no, the plan is incomplete. When executing plans (executing-plans / subagent-driven-development skills), the first action of every session is to read the plan, find the next unchecked box, and start there.

**Enforcement:**
- The writing-plans skill already enforces this (no placeholders, complete code in every step, exact paths).
- New: every plan starts with a 5-line "How to resume" section showing exactly what to read first and how to find the next task.
- Retros (commitment 6) catch plans that turned out to need chat context to execute.

---

### 3. Per-task commit, per-milestone PR, per-plan retro

**Rule:** Three levels of granularity, three artifact types:
- **Task** (one item in a plan) → one git commit. Commit message references the plan + task number (e.g., `feat(agent): cost tracker (Plan 1, Task 6)`).
- **Milestone** (a logical group of tasks, named in the plan) → one PR. PR is auto-merged after CI passes. PR title references the plan + milestone (e.g., `Plan 1 Milestone 1: engine extraction`).
- **Plan** (a complete document like Plan 1) → one retro doc when the plan completes, in `docs/retros/YYYY-MM-DD-<plan-name>-retro.md`.

**Why:** Granularity matters. Big commits hide bugs. Big PRs are unreviewable. Plans without retros calcify mistakes into the next plan. Past pattern: commits batching multiple tasks make it impossible to bisect a regression to a specific change.

**How to apply:** During plan execution, commit after every task's tests pass (the writing-plans skill already prescribes this). Push and PR after every milestone's tasks are all complete. Write a retro within 24 hours of plan completion.

**Enforcement:**
- The writing-plans skill prescribes per-task commits.
- New: a plan's milestone definitions explicitly list "PR title" and "PR exit criteria" so the next session knows when to open the PR.
- New: a `docs/retros/RETRO_TEMPLATE.md` to make retros zero-friction.

---

### 4. Pre-commit hooks gate quality

**Rule:** The cosinabox repo (when it exists) ships with pre-commit hooks that run `ruff`, `mypy`, `pytest` (on changed files), and a secret scan. Any commit that doesn't pass is rejected at the git level. No bypass without an explicit user instruction.

**Why:** Discipline that depends on remembering to run tests is discipline that fails under pressure. Pre-commit hooks make quality the default. Past pattern (across projects, not specifically cos-agent): "I'll fix it later" drift on lint warnings, type errors, and skipped tests. They never get fixed; they accumulate.

**How to apply:** First task in cosinabox repo creation (Plan 1, Phase 1) installs the hooks. Hooks are documented in the engine-repo CLAUDE.md as part of the "developer setup" section.

**Enforcement:**
- `pre-commit` Python package (`pre-commit install` on clone).
- CI in `.github/workflows/test.yml` runs the same checks so a commit that bypasses local hooks still fails CI.
- The PR auto-merge will not fire if CI is red.

---

### 5. Dogfood the discipline pattern in the engine repo's CLAUDE.md

**Rule:** The cosinabox engine repo ships with a top-level `CLAUDE.md` that mirrors the structure of the user-repo `CLAUDE.md` (the one shipped to end-users). The user-repo CLAUDE.md teaches end-users how to be disciplined CoSinaBox stewards. The engine-repo CLAUDE.md teaches Rovik and Claude how to be disciplined cosinabox developers. Same sections: safety rules, quality rules, workflow rules, proactive suggestions.

**Why:** If the engine ships discipline guidance to its users, the engine itself should be developed under the same discipline. Otherwise we're hypocrites. Also: by dogfooding the CLAUDE.md pattern, we discover its weaknesses early. If our own CLAUDE.md is hard to follow, the user-repo one will be too.

**How to apply:** The engine-repo CLAUDE.md is a deliverable in Plan 1, Task 4 (already listed). Its content is drafted in `docs/superpowers/plans/2026-04-11-cosinabox-engine-claude-md.md` as a planning artifact and committed to Cantina before Plan 1 begins. When the cosinabox repo is created, the file moves there.

**Enforcement:**
- The engine-repo CLAUDE.md is read by every Claude Code session that opens the cosinabox repo. The harness loads it automatically.
- A short script (`scripts/lint-claude-md.py`, ships with cosinabox eventually) checks both the engine and user-repo CLAUDE.md files for the canonical sections so they don't drift.

---

### 6. Honest task estimates and slippage tracking

**Rule:** Each task in a plan gets a rough estimate (5 min / 30 min / 2 hr / 1 day). When a task takes meaningfully longer (say >2x), the actual time is recorded in the milestone retro. After a few milestones, calibration improves and estimates get better.

**Why:** Estimates aren't a contract — they're a model. Without them, you can't tell if a project is on track or sliding. Past pattern: "Plan 1 should take 3 weeks" with no internal benchmarks, so by week 6 you have no idea whether you're on track or wildly behind. The discipline isn't "always be right about estimates" — it's "always notice when you weren't, and update the model."

**How to apply:** When writing plans, add `**Est:** 30 min` to each task header. When executing plans, mentally note how long the task actually took (or check git timestamps). At milestone retro, list the 3 tasks that overshot worst and ask why.

**Enforcement:**
- Plan template includes an estimate field per task (writing-plans skill should add this).
- Retro template includes an "estimate calibration" section.

---

### 7. End-of-session ritual (foreground tests, cleanup, memory)

**Rule:** Every session that touched code or substantive docs ends with:
1. Run `pytest` in the foreground (not background-and-poll — see `feedback_test_run_speed.md`).
2. Run lint/type checks if applicable.
3. Stage and commit any uncommitted work, OR explicitly note to the user what's uncommitted and why.
4. If there's unmerged work that's complete, push the branch and open a PR with `--auto` (see `feedback_auto_merge.md`).
5. If a lesson was learned this session, save it as a memory note immediately.
6. If there are stale branches or worktrees from this or earlier sessions, list them for cleanup (see `feedback_cleanup_end_of_session.md`).

**Why:** Sessions that end mid-task leave orphan state — uncommitted changes, unmerged branches, stale worktrees, lessons in conversation that never make it to memory. Past pattern: come back next session to "what was I doing?" The end-of-session ritual prevents this.

**How to apply:** When the user signals end of session (or when natural milestone completion is reached), Claude initiates the ritual without being asked. The ritual is short, ~3-5 minutes, and produces a clean session-end state.

**Enforcement:**
- Memory rule `feedback_autorun_tests_end_of_session.md` already commits to step 1.
- Memory rule `feedback_cleanup_end_of_session.md` already commits to step 6.
- New: a `cantina-dev session-end` shell script (or eventually `cosinabox-dev session-end` in the cosinabox repo) runs the ritual as a single command.

---

### 8. Brainstorm-first for any non-trivial change

**Rule:** No improvising features mid-execution. If a task in a plan turns out to need a design change (the spec was wrong, the architecture doesn't fit, a new requirement surfaces), STOP execution, return to the brainstorming skill, update the spec, update the plan, then resume. No silent drift.

**Why:** Plans are contracts with future-self. Silent drift makes future sessions distrust the plan, which collapses commitment 2 (plan as source of truth). Past pattern: "I'll just add this small thing while I'm here" turns into 5 small things that aren't in the plan, aren't in the spec, and accumulate technical debt no one tracks.

**How to apply:** When mid-task and the design feels wrong, the next action is `Skill superpowers:brainstorming` with a focused prompt: "I'm executing Task N of Plan X and ran into [problem]. Need to revise [section]." The brainstorming session updates the spec and plan, then execution resumes.

**Enforcement:**
- Self-discipline + feedback memory `feedback_upstream_sounding_board.md`.
- Retros catch silent drift after the fact: any commit that touches files not mentioned in the plan is flagged in the retro for "was this drift?"

---

## Process for adding new commitments

This document is not in stone. New commitments come from real failures or near-misses observed in retros. To add one:

1. Name the failure mode in a retro doc.
2. Propose a rule + enforcement mechanism.
3. Add it to this doc with a date.
4. If the mechanism is a hook or script, install it in the same PR.

Commitments without enforcement mechanisms are tolerated for one cycle (one milestone or one week), then either gain a mechanism or get removed.

## Process for retros

After every plan completes (and after every milestone of a long plan), write a retro in `docs/retros/YYYY-MM-DD-<plan-name>-retro.md`. Use `docs/retros/RETRO_TEMPLATE.md` as the starting point. The retro answers:

1. What did we ship vs what we planned?
2. What went well that we should keep doing?
3. What went poorly that we should change?
4. Which estimates were off, and by how much?
5. Did any commitments from this doc get violated? Why?
6. New lessons that should become memory notes or new commitments?

Retros are short (15-30 min to write). They are not optional.

---

## Open items (committed to but not yet installed)

These are gaps where the commitment is real but the mechanism doesn't exist yet because the dependency hasn't been built. Each has an owner-task that installs the mechanism.

| Gap | Mechanism | Installed by |
|---|---|---|
| Pre-commit hooks for cosinabox | `pre-commit` config + ruff/mypy/pytest/secret-scan | Plan 1, Task 4 (cosinabox repo creation) |
| Engine-repo CLAUDE.md | `cosinabox/CLAUDE.md` | Plan 1, Task 4 — content drafted in `docs/superpowers/plans/2026-04-11-cosinabox-engine-claude-md.md` |
| ~~`cantina-dev session-end` script~~ | ✅ `scripts/cantina-dev` (installed 2026-04-12 in PR following the discipline framework) | done |
| Plan template estimate field | Update writing-plans skill or convention | Lightweight — applied manually until baked into the skill |
| ~~Retro template~~ | ✅ `docs/retros/RETRO_TEMPLATE.md` (installed in the discipline framework PR) | done |
| `gh pr merge --auto` enablement on `cantina-memory-service` | Repo-level setting + branch protection | **Manual** — see "Manual setup steps" below |

## Manual setup steps (one-time, per repo)

These are setup actions that can't be automated from a Claude Code session because they require GitHub repo-admin permissions the personal access token doesn't grant. They are one-time fixes per repo.

### Enable `gh pr merge --auto` on a repo

`gh pr merge --auto` requires the repo to have:
1. **Repo setting `Allow auto-merge` enabled** (Settings → General → Pull Requests → Allow auto-merge).
2. **A branch protection rule on `main`** with at least one required status check OR required reviewer OR required conversation resolution. Without this, GitHub has no condition to wait on, so `--auto` is rejected.

**Steps for `cantina-memory-service` (1-2 min, one-time):**

1. Open https://github.com/rovikrobert/cantina-memory-service/settings
2. Under "Pull Requests" check **Allow auto-merge** and **Automatically delete head branches**. Save.
3. Open https://github.com/rovikrobert/cantina-memory-service/settings/branches
4. Click **Add branch protection rule** for `main`.
5. Check **Require conversation resolution before merging** (cheapest gate — no CI required). Save.
6. Verify with: `gh api repos/rovikrobert/cantina-memory-service --jq '.allow_auto_merge'` → should be `true`.

After this, all future PRs created against `cantina-memory-service` can use:

```bash
gh pr create --title "..." --body "..." && gh pr merge --auto --squash --delete-branch
```

If a future repo (e.g., `cosinabox` once it exists) also needs `--auto`, repeat the same steps for that repo.

### Why this matters

`--auto` is the primary defense against the race condition where two concurrent Claude Code sessions try to merge two different PRs at the same time and trample each other. Without `--auto`, both merges happen sequentially under whoever wins the race; with `--auto`, GitHub queues them and merges in order. See `feedback_auto_merge.md`.

---

## Retro template (committed alongside this doc)

See `docs/retros/RETRO_TEMPLATE.md`.

---

## Related memory files

These existing feedback memories codify pieces of the same discipline. The discipline framework above is the system; these are individual rules within the system.

- `feedback_use_worktrees.md` — #1 RULE worktrees
- `feedback_no_stash_recovery.md` — never stash to switch branches
- `feedback_worktree_path.md` — subagent worktree path discipline
- `feedback_red_green_tdd.md` — TDD mandatory
- `feedback_tests_before_deploy.md` — pytest before deploy
- `feedback_autorun_tests_end_of_session.md` — end-of-session pytest
- `feedback_cleanup_end_of_session.md` — end-of-session cleanup
- `feedback_auto_merge.md` — `--auto` flag on PR merge
- `feedback_test_run_speed.md` — foreground pytest, not background-and-poll
- `feedback_no_rebriefing.md` — trust the system, don't re-explain
- `feedback_upstream_sounding_board.md` — engage early, push back
- `feedback_close_loop_on_external_actions.md` — close the loop in-system
- `feedback_post_meeting_debrief.md` — proactive 2-min debrief
- `feedback_dry_run_loop_for_prompts.md` — measure don't guess on prompts

The discipline framework is the umbrella; these are the load-bearing rules under it.
