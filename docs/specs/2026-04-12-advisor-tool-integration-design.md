# Advisor Tool Integration — Design Spec

**Date:** 2026-04-12
**Status:** Approved
**Scope:** Add Claude Advisor Tool (beta) to Keevs' existing Claude API calls

## Problem

Keevs currently routes strategic tasks to full Opus, then downgrades to Sonnet after the first iteration for tool-loop processing. This works but is expensive — the full Opus first turn processes all input tokens at Opus rates. The Advisor Tool (beta) lets a Sonnet executor consult Opus mid-generation server-side, getting near-Opus strategic quality at ~60-70% less cost.

## Approach

**Advisor replaces Opus routing.** Tasks that currently route to Opus instead route to Sonnet executor + Opus advisor. The "Opus first iteration, downgrade to Sonnet" pattern is removed. Simple Sonnet tasks stay as-is.

## Design

### 1. Router (`src/router.py`)

The router returns a `use_advisor` flag alongside model and thinking config.

**Current return:** `(model, thinking, matched_rule)` from `select_model_with_overrides`
**New return:** `(model, thinking, matched_rule, use_advisor)`

Routing table:

| Signal | Current | New |
|--------|---------|-----|
| Opus signals | `(opus, adaptive)` | `(sonnet, None, True)` |
| Moderate signals | `(sonnet, adaptive)` | `(sonnet, None, True)` |
| Conversation escalation | `(opus, adaptive)` | `(sonnet, None, True)` |
| Everything else | `(sonnet, None)` | `(sonnet, None, False)` |
| Sonnet overrides | `(sonnet, None)` | `(sonnet, None, False)` |

Extended thinking on the executor is dropped when advisor is active — the advisor's thinking replaces it, avoids double-paying for reasoning.

The router checks `ADVISOR_ENABLED` before returning `use_advisor=True`. If disabled, falls back to current Opus routing behavior.

`select_model` (the non-async version) also updated to return `use_advisor` as a third element for consistency.

### 2. API Call (`src/agent_failover.py`)

New parameter on `call_with_failover`: `use_advisor: bool = False`

When `use_advisor` is True:
- Append advisor tool definition to tools list:
  ```python
  {"type": "advisor_20260301", "name": "advisor", "model": "claude-opus-4-6", "max_uses": ADVISOR_MAX_USES}
  ```
- Use `client.beta.messages.create(betas=["advisor-tool-2026-03-01"], **call_kwargs)` instead of `client.messages.create(**call_kwargs)`

When False: current path unchanged.

Failover behavior: if Sonnet+advisor fails with 429/529, fall through to Haiku without advisor (advisor requires Opus backend — degrade gracefully on rate limit).

`max_uses` defaults to 2 (one for initial planning, one for mid-task correction). Configurable via `ADVISOR_MAX_USES` env var.

### 3. Agent Loop (`src/agent.py`)

**Pass `use_advisor` through** to `call_with_failover`.

**Opus downgrade logic (lines 820-829):** Kept as fallback for `model_override` cases (scheduled jobs can force Opus directly), but advisor paths skip it since executor is always Sonnet.

**Response content handling — no changes needed:**
- `stop_reason == "end_turn"`: extracts `block.type == "text"` — skips `server_tool_use` and `advisor_tool_result` blocks automatically
- `stop_reason == "tool_use"`: passes `response.content` back as-is — advisor blocks round-trip correctly
- Tool loop iterates `block.type == "tool_use"` only — `server_tool_use` ignored correctly

**History stripping edge case:** If conversation history contains `advisor_tool_result` blocks but the current turn routes to plain Sonnet (no advisor), the API returns 400. Fix: extend `_prune_old_tool_results` to strip `server_tool_use` and `advisor_tool_result` blocks from history when `use_advisor` is False.

**Cost tracking:** After `call_with_failover` returns, check for `response.usage.iterations`. If present, use `estimate_cost_with_advisor()`. Otherwise use existing `estimate_cost`.

### 4. Cost Tracking (`src/cost_tracker.py`)

New function `estimate_cost_with_advisor(model, iterations)`:
- `type: "message"` iterations → bill at executor model rates
- `type: "advisor_message"` iterations → bill at `iteration["model"]` rates (Opus)
- Sum all iteration costs

Budget impact: Advisor calls are typically 1,400-1,800 total tokens (including thinking). At Opus rates: ~$0.02-0.03 per call. With `max_uses: 2`, worst case adds ~$0.06 to a message — well within $0.75 per-message cap.

### 5. Settings (`config/settings.py`)

```python
ADVISOR_ENABLED = os.getenv("ADVISOR_ENABLED", "true").lower() == "true"
ADVISOR_MAX_USES = int(os.getenv("ADVISOR_MAX_USES", "2"))
```

Kill switch defaults on. Can disable without code deploy.

### 6. Tests

- **test_router.py**: Update existing tests — Opus signals now return `(sonnet, None, True)`. Add test for `ADVISOR_ENABLED=False` fallback.
- **test_cost_tracker.py**: Add test for `estimate_cost_with_advisor()` with mock iterations array.
- **test_agent.py**: Add test that advisor blocks get stripped from history when `use_advisor=False`.

No new test files — extend existing ones.

## Files Changed

| File | Change |
|------|--------|
| `config/settings.py` | Add `ADVISOR_ENABLED`, `ADVISOR_MAX_USES` |
| `src/router.py` | Return `use_advisor` flag, drop Opus as executor for advisor paths |
| `src/agent_failover.py` | Accept `use_advisor`, beta API path, advisor tool injection |
| `src/agent.py` | Pass `use_advisor` through, strip advisor blocks from history, advisor cost tracking |
| `src/cost_tracker.py` | Add `estimate_cost_with_advisor()` |
| `tests/test_router.py` | Update routing expectations |
| `tests/test_cost_tracker.py` | Add advisor cost test |
| `tests/test_agent.py` | Add advisor block stripping test |
