# Retro — Research Digest (intel pipeline port), core

**Plan:** `docs/plans/2026-08-20-port-intel-core.md`
**Executed:** 2026-09-07, in one session
**Shipped:** 5 milestones, 12 tasks, 5 PRs (#99, #100, #101, #102, and this one)

## What landed

The legacy intel pipeline's core is now a generic, config-driven
`research_digest` job: `research.yaml` → collect → classify → synthesize →
store → notify. 63 new tests. Nothing hardcodes an org, a person, a domain or
a region key.

The migration note's items map one-to-one:

| Scar | Where it landed |
|---|---|
| Streamed synthesis (the truncation fix) | Tasks 7–8 |
| Alert on zero-signal and near-ceiling | Task 9 |
| Signals as the durable record, with a backup | Tasks 10–11 |
| Failed read ≠ empty file | Deferred with publication, restated in that plan |
| Dead-man's switch | Shipped separately as #98 before this port started |

## What the plan got right

**Interfaces declared per task.** Every task listed what it consumed and
produced, and the self-review notes cross-checked type consistency between
tasks 2/4/6/8. Nothing had to be reworked when a later task consumed an
earlier one — the `SearchBackend` protocol matched `TavilyTool.search`
exactly, and `synthesis_alerts` consumed precisely the triple the job
assembles.

**It predicted its own weakest point.** The self-review notes said
"registration is the one place to read before writing" and named Task 12's
snippet as the only non-self-contained code. That was exactly right, and it
saved time by telling me where to be careful.

**Scars in the plan, not just in the code.** Each default carries a comment
explaining the failure that produced it. `cap_by_priority` sorts before
slicing *because* slicing in append order once cut a region out of the digest
for eleven weeks. That context is why the implementation didn't drift.

## Where the plan was wrong

Four defects, all in code the plan supplied verbatim. Each was caught by the
gates, none by reading.

1. **`feeds.py` didn't type-check** (3 errors). `feedparser` has no stubs;
   `datetime(*stamp[:6], tzinfo=UTC)` is rejected because an unbounded unpack
   can collide with the `tzinfo` keyword; `entry_date` needed an annotation
   and an explicit `None` check. Fixed by indexing year/month/day explicitly —
   which is also more honest, since only the date is compared.

2. **Task 7's test built an un-constructable exception.**
   `anthropic.APIStatusError(..., response=SimpleNamespace(status_code=529))`
   raises `AttributeError` inside the SDK constructor, which dereferences
   `response.request`. The test failed for the wrong reason. This repo already
   had `_FakeAPIError` in `test_agent_failover.py`; reused it.

3. **Task 10's accessors bypassed `Memory.lock`.** The `Memory` docstring is
   explicit that direct `_conn` users must acquire it first — sqlite3
   connections aren't thread-safe for concurrent cursor use even with
   `check_same_thread=False`, and APScheduler, Telegram and the sub-agents
   share this one. The plan's snippet would have introduced a real race.

4. **Task 12's registration referenced three locals that don't exist.**
   `loop.model` (AgentLoop has no such attribute — the Router picks per
   message), `notify_error`, and `config_dir`. Plus `os` wasn't imported.
   The plan warned about this task specifically, which is why it cost minutes
   rather than a debugging session.

**Lesson:** a plan detailed enough to supply verbatim code is worth writing,
but its code is a draft, not an artifact. The value was in the *decisions* and
the recorded scars; the snippets needed the same gates as hand-written code.
Every one of these four was caught by `mypy` or a failing test, so the plan's
insistence on running all four gates per milestone did its job.

## Process note

Two commits were lost to a pre-commit formatter rollback and then silently
squashed, because a failed commit left files staged and the next `git commit`
swept them in. Caught by checking `git show --stat` after the commit rather
than trusting the "N files changed" output. Worth checking the branch head
after any commit where pre-commit reports a rollback.

## Deliberate gaps

- **Publication is not ported.** `digest_publisher.py` (901 lines: GitHub
  markdown + CSV, deep dives, glossary, curriculum, site index) needs its own
  plan, and must carry the #187 scar that a failed read is not an empty file.
- **Stage 3 (follow-up searches) is not ported.** `follow_up_signals` is
  captured and stored, but nothing acts on it — a genuine feature loss versus
  the legacy pipeline. Belongs in the publication plan, where its output has
  somewhere to go. (Relatedly, cos-agent #203 removed the one Stage 3 output
  that had no destination there either.)
- **The legacy job stays on.** Per the plan: run both for at least two weeks
  and compare digests before switching `asia_lab_tracker` off.

## Next

1. Compare output against the legacy digest for two weeks.
2. Plan the publication milestone.
3. Add Stage 3 to that plan.
