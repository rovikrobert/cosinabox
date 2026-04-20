# Retro: port `commitments` + `auto_resolve` from cos-agent

**Plan:** `docs/plans/2026-04-19-port-commitments-auto-resolve.md`
**PR:** cosinabox#60
**Date:** 2026-04-19

## Estimated vs actual

| Milestone | Estimated | Actual (rough) | Notes |
|---|---|---|---|
| M1 schema + CRUD | 3h | ~45m | SQLite translation was mechanical once the DDL was written. |
| M2 auto_resolve | 4h | ~45m | Dropping Drive search shaved most of it. ThreadPoolExecutor port was one-for-one. |
| M3 wire briefings | 2h | ~30m | Grounded mode vs no-db fallback was a clean conditional. |
| M4 morning briefing | 1h | ~15m | Smallest change — single section. |
| M5 tools | 3h | ~45m | Most weight went into tool descriptions, not logic. |
| M6 docs + CLI | 2h | ~20m | Skipped the simulate fixture; the `describe` counts were a one-shot. |
| M7 commit/PR | 30m | 15m | Split commits by milestone for review. |
| M8 inventory + retro | 30m | 20m | This doc. |
| **Total** | **~16h** | **~4h** | Estimate was ~4× actual. |

## What surprised me

- **ThreadPoolExecutor was fine.** I worried the sync fan-out would look janky vs asyncio.gather; in practice five workers + a per-item timeout was the same ~20 LOC.
- **Keyword heuristics travel poorly.** cos-agent's stop-word list was tuned for Cantina-style subjects; the tests caught two cases where the port's extraction was too aggressive until I preserved the full cos-agent list.
- **Drive search deferral was the right call.** No tests, no wiring, no extra OAuth scope in v1 kept the PR surface focused.
- **The "no db fallback" path doubled the test coverage for free.** Every briefing job now has both a grounded and a defensive test, which was not on the plan but fell out of making the `db` param optional.

## What I'd change next time

- **Collapse M3 + M4 up-front.** I split them in the plan for reviewer clarity, but they touched the same prompt-structure pattern and ended up being one commit anyway. Future briefing-grounding plans: one milestone.
- **Test the `describe` CLI earlier.** I caught the "no commitments" vs "silently omitted" UX only at M6 when adding the test. Should have been a plan assertion.
- **The CRUD `list_commitments(status_filter=None)` default was ambiguous** — it meant "open only" inside the CRUD layer but "all" from the tool. Caused one test failure during M5. If I'd typed it as `Literal["open"] | list[str] | _All`, the mypy pass would have caught it.

## Follow-ups (none blocking cutover)

1. Drive search in `auto_resolve` — plan noted, not filed.
2. Auto-creation of commitments from chat / email / meeting — the source columns are ready. Wiring needs an extraction prompt and a conservative policy rule.
3. Commitment history / audit log beyond `manual_closures` — only needed if users start asking "who changed what when."
4. Async wrapper on the verifier — only if a future scheduler refactor demands it.
5. Re-run the `rovik-keevs` 2026-04-18 evening wrap with the new grounding to confirm the zombie items are gone in production.

## Remaining cos-agent ports (after this PR)

Still tagged `port` in the cutover inventory:

- `consult` (advisor tool — likely small)
- Keep Warm (phases 1–3) — multi-file, spans Attio custom fields
- `analytics` / `cost_tracker` — mark as "audit gap," diff-and-port
