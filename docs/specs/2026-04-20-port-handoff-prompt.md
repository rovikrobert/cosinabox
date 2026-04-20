# Handoff prompt — remaining cos-agent → cosinabox ports

Paste the body below into a fresh Claude Code session to resume porting work. It's self-contained: no prior-session context required.

---

I'm continuing the cos-agent → cosinabox port. The critical-path inventory has drained and only `port-later` items remain. Read the cutover inventory at `~/code/cos-agent/docs/superpowers/specs/2026-04-17-cosinabox-cutover.md` — it's the source of truth for what's ported and what isn't.

## Remaining backlog

In rough priority order:

### 1. `consult` — MCP server endpoint (scope written, plan pending)

Scope doc: `docs/specs/2026-04-20-consult-scope.md`. It proposes 3 deployment options (bolt-on / standalone CLI / native MCP SDK) with recommendation for native MCP via the `mcp` Python SDK. Open questions are enumerated at the bottom.

**To execute:** answer the 5 open questions, then write an executable plan following the shape of `docs/plans/2026-04-19-port-commitments-auto-resolve.md`. Estimate ~14 hours across 7 milestones. Do NOT execute the plan without first deciding the deployment model — it's load-bearing.

### 2. `decision_memos` (`port-later`)

cos-agent: `~/code/cos-agent/src/decision_memos.py`. Users log decisions with context + options + outcome; briefings surface stale decisions. 2 imports in cos-agent. Low usage signal — **verify the maintainer actually uses this feature in cos-agent** before porting. If unused for 30+ days, propose deprecation instead.

### 3. `lesson_extractor` (`port-later`)

cos-agent: `~/code/cos-agent/src/lesson_extractor.py`. Pulls lessons-learned from meeting transcripts + chat history into a lessons table, surfaced in weekly review. 1 import in cos-agent; 0 user-facing. Same verification step as `decision_memos`.

### 4. `bot_wa_relay` (`port-later`)

cos-agent: `~/code/cos-agent/src/bot_wa_relay.py`. WhatsApp bot adapter. cosinabox is Telegram-first. Only makes sense if we're adding a second channel abstraction. Before porting, write a scope doc on what "second channel" means for cosinabox's adapter layer — likely bigger than a file port.

### 5. `/timezone` command (`port-later`)

cos-agent: `bot_commands.py`. Lets the user change `personality.md:timezone` at runtime. Small. Probably 2-3 hours total including CLI + docs.

### 6. Intel pipeline (`port-later`)

cos-agent: `src/intel/`. Video/audio digest generation, separate scheduler hooks. Maintainer flagged it may deprecate entirely. **Confirm continued use before spending any time.** If confirmed, this is multi-PR.

## Patterns established by prior ports

Follow these:

- **Every non-trivial port gets a plan doc first** (`docs/plans/YYYY-MM-DD-<name>.md`), then execution, then retro (`docs/retros/`). Scope docs (`docs/specs/`) come before plans when the port shape isn't obvious.
- **Split commits by milestone** during execution — makes squash-merge review readable.
- **TDD red-green per milestone.** Write failing tests first; implement to make them pass.
- **Per-tool policy default:** read-only = ALLOW, write = REQUIRE_APPROVAL, SQLite-local side effects = ALLOW. See `cosinabox/agent/policy.py` for precedent.
- **Defaults live in `cosinabox/defaults.py`** with a dated comment explaining *why*.
- **OSS-safe text only** in any user-facing string. No hardcoded names, companies, or domains.
- **Pre-commit ruff pin matches CI ruff version** in `.pre-commit-config.yaml` → both should be recent (0.15.x+ as of 2026-04-20).
- **Module-level cache sentinels use `float('-inf')`**, not `0.0` — CI runners with small `time.monotonic()` break 0.0-sentinel caches.

## How to start

Pick the top-priority item you want to tackle. For `consult`, answer the open questions in the scope doc and write the plan. For anything else, start by confirming the maintainer still uses the feature in cos-agent (git log + their own memory is the truth), then write a scope or plan depending on complexity.

Check active PRs before branching: `gh pr list -R rovikrobert/cosinabox --state open`. PR #51 (debrief persist) was rebased and awaits CI at last check; verify state before opening new branches that might conflict.

---

**End of handoff prompt.**
