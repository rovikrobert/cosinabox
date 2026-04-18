# Plan: Port `agent_failover` from cos-agent to cosinabox

**Status:** Not started.
**Source:** `~/code/cos-agent/src/agent_failover.py` (155 lines).
**Target:** `src/cosinabox/agent/failover.py` (new) — called from `src/cosinabox/agent/loop.py`.
**Cutover tag:** **port** (from the cutover inventory).
**How to resume:** open this file, find the first `- [ ]` milestone, read its "Files touched" + "Tests" sections, start there. Self-contained; do not rely on chat context.

## Context / Why

cosinabox today makes single-model Anthropic API calls (`src/cosinabox/agent/loop.py:280-287`). When the requested model is rate-limited (429) or overloaded (529), the call fails and the circuit breaker trips; the user sees an error and the job output is lost.

cos-agent has a failover helper that walks a model chain (Opus → Sonnet → Haiku) on retriable errors, raises immediately on unrecoverable ones (auth, credit), and returns the model that actually responded so cost tracking is accurate. Porting this lifts cosinabox's reliability without design work — the logic is well-tested and already has 6 months of production use in cos-agent.

This is the smallest `port`-tagged item in the cutover inventory (~1 day), so it's a good first port.

## Non-goals

- No changes to cosinabox's existing circuit breaker (`_consecutive_failures`, `_circuit_breaker_lock`). Failover runs *inside* the existing try/except and only widens the retry surface. The breaker still trips after all models fail.
- No changes to advisor tool wiring. Advisor stays as-is; failover just strips it when the chain falls back to Haiku.
- No changes to `MAX_TOOL_ITERATIONS` or cost tracking logic.
- No new public API surface; the helper is an internal function called from within `AgentLoop._run_model_call` (or wherever the current call lives).
- No extraction of the circuit-breaker into a separate module. Keep it where it is.

## Milestones

### M1 — Write the failing tests

**Files touched:** `tests/unit/test_agent_failover.py` (new).
**Tests:** TDD — these start red.

- [ ] Create test file with the following cases, mocking the Anthropic client:
  - `test_first_model_succeeds_no_failover`: client.messages.create returns a response on the first call → returns `(response, "opus")`, no retries.
  - `test_rate_limit_falls_back_to_sonnet`: opus raises `APIError` with status 429 → retries sonnet → returns `(response, "sonnet")`.
  - `test_overloaded_falls_back`: opus raises 529 "overloaded" → retries sonnet → success.
  - `test_all_models_exhausted_raises`: every model in the chain raises 429 → final `APIError` is re-raised.
  - `test_unrecoverable_credit_error_raises_immediately`: opus raises "credit balance is too low" → no failover, raises immediately.
  - `test_401_auth_error_raises_immediately`: opus raises 401 → no failover.
  - `test_haiku_fallback_strips_advisor`: caller passes `use_advisor=True`; opus + sonnet fail; haiku is reached → advisor tool NOT in the tools list, and the non-beta `messages.create` is used (not `beta.messages.create`).
  - `test_haiku_fallback_strips_thinking`: caller passes `thinking={...}`; falls back to haiku → `thinking` key not in kwargs (haiku doesn't support extended thinking).
  - `test_failover_returns_actual_model_used`: opus fails, sonnet succeeds → return tuple's second element is `"claude-sonnet-4-6"` not `"claude-opus-4-6"`.
  - `test_unknown_model_uses_single_item_chain`: caller passes a model not in `MODEL_FAILOVER_CHAIN` → tries only that model, no failover.
- [ ] Run `pytest tests/unit/test_agent_failover.py -v` — confirm all fail with `ModuleNotFoundError`.

**Estimate:** 45 min.

### M2 — Port the helper

**Files touched:** `src/cosinabox/agent/failover.py` (new), `src/cosinabox/defaults.py`.
**Tests:** M1 tests turn green.

- [ ] Add `MODEL_FAILOVER_CHAIN` to `src/cosinabox/defaults.py`:
  ```python
  # API failover chain. On 429/529/overloaded, the agent walks this list
  # from the requested model forward. Chosen 2026-04-11 (originally in
  # cos-agent) — Opus for strategy, Sonnet as workhorse, Haiku as the
  # last-resort reply-with-something model. Ported to cosinabox 2026-04-17.
  MODEL_FAILOVER_CHAIN: tuple[str, ...] = (
      "claude-opus-4-6",
      "claude-sonnet-4-6",
      "claude-haiku-4-5-20251001",
  )
  ```
- [ ] Create `src/cosinabox/agent/failover.py` with:
  - `call_with_failover(client, model, *, system, tools, messages, max_tokens=None, thinking=None, use_advisor=False) -> tuple[object, str]`
  - Body mirrors cos-agent's `agent_failover.py:28-115` but:
    - Drop the global `_consecutive_api_failures` and circuit breaker — cosinabox has its own in `loop.py`.
    - Drop `_notify_circuit_break` — cosinabox handles breaker alerts elsewhere.
    - Read `MODEL_FAILOVER_CHAIN` from `cosinabox.defaults`.
    - Advisor constants (`_ADVISOR_TOOL`, `_ADVISOR_BETA`) — import from `cosinabox.agent.loop` if already defined there, or duplicate them here (check first).
  - Synchronous function (cosinabox's `AgentLoop.run` is sync at the API-call layer; don't make this async).
- [ ] Run M1 tests — all green.

**Estimate:** 45 min.

### M3 — Wire into the loop

**Files touched:** `src/cosinabox/agent/loop.py`.
**Tests:** existing suite stays green.

- [ ] Replace the single-call block (loop.py:278-287) with a call to `call_with_failover`:
  ```python
  from cosinabox.agent.failover import call_with_failover

  response, model_used = call_with_failover(
      self.client,
      model,
      system=call_kwargs.get("system"),
      tools=effective_tool_definitions,
      messages=call_messages,
      max_tokens=4096,
      thinking=thinking,
      use_advisor=use_advisor,
  )
  ```
- [ ] Update cost tracking: pass `model_used` (not `model`) to whatever records cost. Grep for `self.cost.add` or similar in `loop.py` and confirm the model is recorded correctly.
- [ ] Run full suite: `pytest`. Existing tests that pre-stub `client.messages.create` should still pass (failover wraps but preserves single-call semantics when first model succeeds).

**Estimate:** 20 min.

### M4 — Commit, PR, merge

**Files touched:** none (git only).

- [ ] Commit as: `feat(agent): model-chain failover on 429/529 (ported from cos-agent)`.
- [ ] PR body: link to this plan + cos-agent source reference + call out the cost-tracking change (model_used, not model).
- [ ] `gh pr create ... && gh pr merge --auto --squash`.

**Estimate:** 10 min.

### M5 — Update cutover inventory

**Files touched:** `~/code/cos-agent/docs/superpowers/specs/2026-04-17-cosinabox-cutover.md`.

- [ ] In the missing-feature table, change `agent_failover` row from `port` to `ported 2026-04-17`.
- [ ] Commit in cos-agent with `docs: mark agent_failover as ported`.
- [ ] PR + merge.

**Estimate:** 10 min.

## Out of scope / follow-ups

- **Async failover.** If cosinabox's agent loop ever goes async, convert `call_with_failover` to async then. Not now.
- **Exponential backoff between retries.** cos-agent doesn't have it; porting as-is. Consider later if 429s start stacking.
- **Advisor tool + Haiku combination.** Haiku doesn't support advisor. The fallback strips it silently. If users notice strategic-quality regressions on Haiku fallback, consider surfacing a warning.
- **Configurable chain.** cos-agent's chain is hardcoded; cosinabox inherits that. If users want per-deployment chains later, add to `integrations.yaml` or `defaults.py` override path.

## Total estimate

~2 hours including M5. The spec said "~1 day" — this plan is tighter because cos-agent's implementation is small and the test surface is well-defined.
