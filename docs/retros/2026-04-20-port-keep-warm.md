# Retro: port Keep Warm from cos-agent

**Plan:** `docs/plans/2026-04-20-port-keep-warm.md`
**PR:** cosinabox#63 (stacked on #62)
**Date:** 2026-04-20

## Estimated vs actual

| Milestone | Estimated | Actual (rough) | Notes |
|---|---|---|---|
| M1 parse fields | 90m | ~20m | New `_first_value` helper made the missing/corrupt field cases trivial. |
| M2 list + overdue | 2h | ~30m | Sort key handles `None` days_since cleanly; the wrap-any-error-as-empty pattern means no new exception surfaces. |
| M3 set + unset | 90m | ~15m | Cadence clamping at `[1, 365]` caught one test via bounds. |
| M4 briefing wiring | 2h | ~30m | Existing `attio` tool already plumbed through `tool_instances`; only new wire was constructor param. Prompt conditional mirrors the `db` pattern from the commitments port. |
| M5 tools + policy | 2h | ~25m | Tool-description text was the longest part. |
| M6 docs | 1h | ~15m | Small adds. |
| M7 commit / PR | 30m | ~20m | 4 logical commits. |
| M8 retro + inventory | 30m | ~15m | This doc. |
| **Total** | **~10h** | **~2.5h** | 4× faster than the estimate. |

## What went well

- **Stacked PR worked cleanly.** Basing on `feat/analytics-gap` (which held the plan doc) and having the commitments pattern as prior art meant zero architectural decisions during execution.
- **Discovered a real bug.** The CI flake in `test_summary_formats_for_system_prompt` uncovered a `time.monotonic()` edge case in `_ERROR_SUMMARY_AT` init: initializing to `0.0` made the first cache read look fresh on a freshly-booted Python process. Fixed with `float('-inf')` sentinel. Would have shipped broken on any future short-lived Lambda / ephemeral runtime without the CI failure surfacing it.
- **Attio abstraction handled `_normalize` extensions without rewriting callers.** Adding 4 new fields didn't break any of the 10+ existing call sites.

## What surprised me

- **Attio API shape is fragile.** `first or _first_str('value')` chains got messy; refactored to a single `_first_value` helper that returns raw values, then cast at the call site. Cleaner and covers the "corrupt list of strings" edge case that the cos-agent port surfaced a year ago.
- **The test helper bug.** My `_record` fixture used `name.split()[-1]` which equals `split()[0]` for single-word names, producing "Known Known." Two tests failed before I caught it. Lesson: test fixtures are code; write defensively.
- **Plan estimate was generous.** 10h → 2.5h. The commitments port had the same overrun (16h → 4h). Pattern: once the architectural pattern is set (commitments laid the groundwork), subsequent ports are mostly typing.

## What I'd change next time

- **Add `autouse` cache-reset fixtures** to every test module that touches module-level state. Caught one flake in CI; could have prevented it in the first place.
- **Use `float('-inf')` as the default cache-miss sentinel** in any new caching layer from day one.
- **Write the helper fixture tests first.** Even quick fixtures deserve a smoke test; would have caught the "Known Known" bug in seconds.

## Follow-ups (not blocking cutover)

1. **Seed script** — flip `stakeholders.yaml` entries into Keep Warm on first Attio enable. One-line onboarding win.
2. **Keep Warm history** — track cadence changes over time for relationship-health trend analysis.
3. **Batch-set cadence** — conversational "mark all my investors with 7-day Keep Warm" would need bulk PATCHing; plan how without N+1 API calls.
4. **Relationship health score** (cos-agent's `compute_relationship_health`) — separate port, Attio-dependent, less urgent now that Keep Warm covers the overdue-surfacing case.
5. **CLI commands** `cosinabox keep-warm set/unset/list` — low priority; conversational flow works.

## Remaining cos-agent `port`-tagged items

- `consult` (actually a full MCP HTTP endpoint — separate scope doc needed).
- `analytics` / `cost_tracker` diff — **done in PR #62**.
- `auto_resolve` Drive search — deferred, needs Drive tool first.

Port queue is nearly drained. Next is the commitments auto-creation extraction pipeline (not in inventory but blocks the "set it and forget it" UX).
