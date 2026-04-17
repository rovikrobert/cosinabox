# Advisor Tool Integration — Implementation Plan

**Status:** Completed 2026-04-12.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Replace Keevs' Opus-first-then-downgrade pattern with Sonnet executor + Opus advisor, getting near-Opus quality at ~60-70% less cost.

**Architecture:** The router returns a `use_advisor` flag instead of routing to Opus directly. When active, `call_with_failover` injects the advisor tool and uses the beta API. The agent loop passes the flag through unchanged — response handling works automatically since `server_tool_use` and `advisor_tool_result` blocks are skipped by existing content filters.

**Tech Stack:** Python 3.11+, Anthropic Python SDK (beta API), pytest

**Spec:** `docs/superpowers/specs/2026-04-12-advisor-tool-integration-design.md`

---

### Task 1: Settings — add advisor config

**Files:**
- Modify: `config/settings.py:48-57`

- [x] **Step 1: Add advisor settings**

Add after line 57 (after `MODEL_FAILOVER_CHAIN`):

```python
# Advisor tool (beta) — Sonnet executor consults Opus advisor server-side
ADVISOR_ENABLED = os.getenv("ADVISOR_ENABLED", "true").lower() == "true"
ADVISOR_MAX_USES = int(os.getenv("ADVISOR_MAX_USES", "2"))
```

- [x] **Step 2: Commit**

```bash
git add config/settings.py
git commit -m "feat: add ADVISOR_ENABLED and ADVISOR_MAX_USES settings"
```

---

### Task 2: Cost tracker — add advisor iteration billing

**Files:**
- Modify: `src/cost_tracker.py`
- Test: `tests/test_cost_tracker.py`

- [x] **Step 1: Write failing test for `estimate_cost_with_advisor`**

Add to `tests/test_cost_tracker.py`:

```python
from src.cost_tracker import estimate_cost_with_advisor


class TestEstimateCostWithAdvisor:
    def test_single_executor_iteration(self):
        """No advisor call — just one executor iteration."""
        iterations = [
            {"type": "message", "input_tokens": 1000, "output_tokens": 500,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
        ]
        cost = estimate_cost_with_advisor("claude-sonnet-4-6", iterations)
        expected = (1000 / 1_000_000) * 3.0 + (500 / 1_000_000) * 15.0
        assert cost == pytest.approx(expected)

    def test_executor_plus_advisor(self):
        """Sonnet executor + Opus advisor + Sonnet resumed."""
        iterations = [
            {"type": "message", "input_tokens": 412, "output_tokens": 89,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            {"type": "advisor_message", "model": "claude-opus-4-6",
             "input_tokens": 823, "output_tokens": 1612,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            {"type": "message", "input_tokens": 1348, "output_tokens": 442,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 412},
        ]
        cost = estimate_cost_with_advisor("claude-sonnet-4-6", iterations)
        # Executor iterations at Sonnet rates
        exec1 = (412 / 1e6) * 3.0 + (89 / 1e6) * 15.0
        exec2 = (1348 / 1e6) * 3.0 + (442 / 1e6) * 15.0 + (412 / 1e6) * 0.30
        # Advisor iteration at Opus rates
        advisor = (823 / 1e6) * 15.0 + (1612 / 1e6) * 75.0
        assert cost == pytest.approx(exec1 + advisor + exec2)

    def test_advisor_with_cache_tokens(self):
        """Advisor iteration with its own cache tokens billed at Opus rates."""
        iterations = [
            {"type": "message", "input_tokens": 500, "output_tokens": 100,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            {"type": "advisor_message", "model": "claude-opus-4-6",
             "input_tokens": 200, "output_tokens": 800,
             "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 500},
        ]
        cost = estimate_cost_with_advisor("claude-sonnet-4-6", iterations)
        exec_cost = (500 / 1e6) * 3.0 + (100 / 1e6) * 15.0
        adv_cost = ((200 / 1e6) * 15.0 + (800 / 1e6) * 75.0
                    + (1000 / 1e6) * 18.75 + (500 / 1e6) * 1.50)
        assert cost == pytest.approx(exec_cost + adv_cost)

    def test_empty_iterations_returns_zero(self):
        cost = estimate_cost_with_advisor("claude-sonnet-4-6", [])
        assert cost == 0.0
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /path/to/worktree/cos-agent && python3 -m pytest tests/test_cost_tracker.py::TestEstimateCostWithAdvisor -v`
Expected: FAIL with `ImportError` (function doesn't exist yet)

- [x] **Step 3: Implement `estimate_cost_with_advisor`**

Add to `src/cost_tracker.py` after the existing `estimate_cost` function:

```python
def estimate_cost_with_advisor(
    executor_model: str,
    iterations: list[dict],
) -> float:
    """Estimate cost from the usage.iterations array returned by advisor-enabled calls.

    - type: "message" iterations are billed at the executor model's rates.
    - type: "advisor_message" iterations are billed at the iteration's own model rates.
    """
    total = 0.0
    for it in iterations:
        if it["type"] == "advisor_message":
            model = it["model"]
        else:
            model = executor_model
        total += estimate_cost(
            model,
            it.get("input_tokens", 0),
            it.get("output_tokens", 0),
            cache_creation_tokens=it.get("cache_creation_input_tokens", 0) or 0,
            cache_read_tokens=it.get("cache_read_input_tokens", 0) or 0,
        )
    return total
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd /path/to/worktree/cos-agent && python3 -m pytest tests/test_cost_tracker.py::TestEstimateCostWithAdvisor -v`
Expected: all 4 PASS

- [x] **Step 5: Run full cost tracker test suite**

Run: `cd /path/to/worktree/cos-agent && python3 -m pytest tests/test_cost_tracker.py -v`
Expected: all existing + new tests PASS

- [x] **Step 6: Commit**

```bash
git add src/cost_tracker.py tests/test_cost_tracker.py
git commit -m "feat: add estimate_cost_with_advisor for advisor tool billing"
```

---

### Task 3: Router — return `use_advisor` flag

**Files:**
- Modify: `src/router.py`
- Test: `tests/test_router.py`

- [x] **Step 1: Write failing tests for advisor routing**

Update existing imports in `tests/test_router.py` — no new imports needed since everything is already imported.

Add a new test class at the end of the file:

```python
class TestAdvisorRouting:
    """Advisor mode: Opus signals and moderate signals return use_advisor=True."""

    def test_opus_signal_returns_advisor(self):
        model, thinking, use_advisor = select_model("Let's discuss the Singapore strategy")
        assert model == "claude-sonnet-4-6"
        assert thinking is None
        assert use_advisor is True

    def test_moderate_signal_returns_advisor(self):
        model, thinking, use_advisor = select_model("Compare these two approaches for the grant")
        assert model == "claude-sonnet-4-6"
        assert thinking is None
        assert use_advisor is True

    def test_conversation_escalation_returns_advisor(self):
        context = [
            {"content": "strategy for Singapore"},
            {"content": "positioning with EDB"},
            {"content": "pre-mortem on the plan"},
            {"content": "what about implications?"},
        ]
        model, thinking, use_advisor = select_model("continue", conversation_context=context)
        assert model == "claude-sonnet-4-6"
        assert thinking is None
        assert use_advisor is True

    def test_simple_query_no_advisor(self):
        model, thinking, use_advisor = select_model("Hey, good morning")
        assert model == "claude-sonnet-4-6"
        assert thinking is None
        assert use_advisor is False

    def test_sonnet_override_no_advisor(self):
        model, thinking, use_advisor = select_model("What's on my calendar today?")
        assert model == "claude-sonnet-4-6"
        assert thinking is None
        assert use_advisor is False

    def test_advisor_disabled_falls_back_to_opus(self, monkeypatch):
        monkeypatch.setattr("src.router.ADVISOR_ENABLED", False)
        model, thinking, use_advisor = select_model("Let's discuss the Singapore strategy")
        assert model == "claude-opus-4-6"
        assert thinking is not None
        assert use_advisor is False
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd /path/to/worktree/cos-agent && python3 -m pytest tests/test_router.py::TestAdvisorRouting -v`
Expected: FAIL — `select_model` returns 2 values, not 3

- [x] **Step 3: Update `select_model` to return 3 values**

In `src/router.py`, add import at the top (after existing imports):

```python
from config.settings import ADVISOR_ENABLED
```

Replace the `select_model` function (lines 98-119) with:

```python
def select_model(
    message: str, conversation_context: list[dict] | None = None
) -> tuple[str, dict | None, bool]:
    """Route to appropriate model. Returns (model, thinking, use_advisor).

    When ADVISOR_ENABLED, Opus signals and moderate signals route to
    Sonnet + Opus advisor instead of Opus or Sonnet+thinking directly.
    """
    msg_lower = message.lower().strip()

    for pattern in SONNET_OVERRIDES:
        if re.search(pattern, msg_lower):
            return "claude-sonnet-4-6", None, False

    for pattern in OPUS_SIGNALS:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            if ADVISOR_ENABLED:
                return "claude-sonnet-4-6", None, True
            return "claude-opus-4-6", THINKING_ADAPTIVE, False

    for pattern in MODERATE_SIGNALS:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            if ADVISOR_ENABLED:
                return "claude-sonnet-4-6", None, True
            return "claude-sonnet-4-6", THINKING_ADAPTIVE, False

    if conversation_context and _conversation_is_strategic(conversation_context):
        if ADVISOR_ENABLED:
            return "claude-sonnet-4-6", None, True
        return "claude-opus-4-6", THINKING_ADAPTIVE, False

    return "claude-sonnet-4-6", None, False
```

- [x] **Step 4: Run new tests to verify they pass**

Run: `cd /path/to/worktree/cos-agent && python3 -m pytest tests/test_router.py::TestAdvisorRouting -v`
Expected: all 6 PASS

- [x] **Step 5: Update existing tests that unpack 2 values from `select_model`**

Every existing test that does `model, thinking = select_model(...)` needs a third variable. Update all call sites:

In `TestSonnetOverrides`: change all `model, _ = select_model(...)` to `model, _, _ = select_model(...)` and `model, thinking = select_model(...)` to `model, thinking, _ = select_model(...)`.

In `TestOpusSignals`: same pattern. **Also update assertions** — Opus signals now return `("claude-sonnet-4-6", None, True)` when advisor is enabled. Since tests run with default settings (`ADVISOR_ENABLED=True`), update:
```python
class TestOpusSignals:
    def test_strategy_keyword(self):
        model, thinking, use_advisor = select_model("Let's discuss the Singapore strategy")
        assert model == "claude-sonnet-4-6"
        assert thinking is None
        assert use_advisor is True

    def test_positioning(self):
        model, _, use_advisor = select_model("How should we position Cantina with EDB?")
        assert model == "claude-sonnet-4-6"
        assert use_advisor is True

    def test_pre_mortem(self):
        model, _, use_advisor = select_model("Run a pre-mortem on the Tech@SG application")
        assert model == "claude-sonnet-4-6"
        assert use_advisor is True

    def test_stress_test(self):
        model, _, use_advisor = select_model("Stress test this plan")
        assert model == "claude-sonnet-4-6"
        assert use_advisor is True

    def test_career(self):
        model, _, use_advisor = select_model("How does this affect my career trajectory?")
        assert model == "claude-sonnet-4-6"
        assert use_advisor is True
```

In `TestModerateSignals`: update similarly — model stays Sonnet but thinking becomes None, use_advisor is True:
```python
class TestModerateSignals:
    def test_compare(self):
        model, thinking, use_advisor = select_model("Compare these two approaches for the grant")
        assert model == "claude-sonnet-4-6"
        assert thinking is None
        assert use_advisor is True

    def test_evaluate(self):
        model, thinking, use_advisor = select_model("Evaluate whether this timeline is realistic")
        assert model == "claude-sonnet-4-6"
        assert thinking is None
        assert use_advisor is True

    def test_how_should_i(self):
        model, thinking, use_advisor = select_model("How should I approach the NUS conversation?")
        assert model == "claude-sonnet-4-6"
        assert thinking is None
        assert use_advisor is True
```

In `TestAdaptiveThinking`: Opus and moderate signals no longer return adaptive thinking when advisor is enabled. Update:
```python
class TestAdaptiveThinking:
    def test_opus_uses_advisor_not_thinking(self):
        _, thinking, use_advisor = select_model("What's the strategy here?")
        assert thinking is None
        assert use_advisor is True

    def test_moderate_uses_advisor_not_thinking(self):
        _, thinking, use_advisor = select_model("Compare these options for the meeting")
        assert thinking is None
        assert use_advisor is True

    def test_operational_gets_no_thinking(self):
        _, thinking, use_advisor = select_model("What's on my calendar?")
        assert thinking is None
        assert use_advisor is False
```

In `TestDefaultSonnet`: add third unpack variable:
```python
class TestDefaultSonnet:
    def test_casual_greeting(self):
        model, thinking, use_advisor = select_model("Hey, good morning")
        assert model == "claude-sonnet-4-6"
        assert thinking is None
        assert use_advisor is False

    def test_simple_question(self):
        model, _, use_advisor = select_model("What's the weather?")
        assert model == "claude-sonnet-4-6"
        assert use_advisor is False
```

In `TestConversationEscalation`: escalation now returns Sonnet + advisor:
```python
class TestConversationEscalation:
    def test_strategic_conversation_escalates(self):
        context = [
            {"content": "Let's think about the positioning strategy"},
            {"content": "What are the trade-offs here?"},
            {"content": "Run a pre-mortem on this"},
            {"content": "What are the second-order implications?"},
        ]
        model, thinking, use_advisor = select_model("continue", conversation_context=context)
        assert model == "claude-sonnet-4-6"
        assert use_advisor is True

    def test_mixed_conversation_stays_sonnet(self):
        context = [
            {"content": "Check my calendar"},
            {"content": "What's the positioning strategy?"},
            {"content": "Send an email to Daniel"},
            {"content": "OK thanks"},
        ]
        model, _, use_advisor = select_model("continue", conversation_context=context)
        assert model == "claude-sonnet-4-6"
        assert use_advisor is False

    def test_no_context_stays_sonnet(self):
        model, _, use_advisor = select_model("continue", conversation_context=None)
        assert model == "claude-sonnet-4-6"
        assert use_advisor is False
```

In `TestRoutingRegression`: update the CORPUS and test method — now returns 3 values, and Opus entries become Sonnet+advisor:
```python
class TestRoutingRegression:
    """Replay corpus — ensures routing doesn't regress on known prompts.

    Each case is (prompt, expected_model, expected_thinking_present, expected_advisor).
    """
    CORPUS = [
        # Operational → Sonnet, no thinking, no advisor
        ("What's on my calendar today?", "claude-sonnet-4-6", False, False),
        ("find email from Daniel", "claude-sonnet-4-6", False, False),
        ("summarize the meeting notes", "claude-sonnet-4-6", False, False),
        ("what time is the call?", "claude-sonnet-4-6", False, False),
        ("draft an email reply to Timo", "claude-sonnet-4-6", False, False),
        ("should i reply to this email?", "claude-sonnet-4-6", False, False),
        ("Hey, good morning", "claude-sonnet-4-6", False, False),
        # Strategic → Sonnet with advisor (was Opus with thinking)
        ("Let's discuss the Singapore strategy", "claude-sonnet-4-6", False, True),
        ("How should we position Cantina with EDB?", "claude-sonnet-4-6", False, True),
        ("Run a pre-mortem on the Tech@SG application", "claude-sonnet-4-6", False, True),
        ("Stress test this plan", "claude-sonnet-4-6", False, True),
        ("What are the second-order implications?", "claude-sonnet-4-6", False, True),
        # Moderate → Sonnet with advisor (was Sonnet with thinking)
        ("Compare these two approaches for the grant", "claude-sonnet-4-6", False, True),
        ("Evaluate whether this timeline is realistic", "claude-sonnet-4-6", False, True),
        ("How should I approach the NUS conversation?", "claude-sonnet-4-6", False, True),
        # Edge: Sonnet override trumps advisor
        ("meeting with Daniel about strategy", "claude-sonnet-4-6", False, False),
    ]

    @pytest.mark.parametrize(
        "prompt,expected_model,expected_thinking,expected_advisor",
        CORPUS,
        ids=[c[0][:40] for c in CORPUS],
    )
    def test_routing_decision(self, prompt, expected_model, expected_thinking, expected_advisor):
        model, thinking, use_advisor = select_model(prompt)
        assert model == expected_model, f"Expected {expected_model} for: {prompt!r}"
        if expected_thinking:
            assert thinking is not None, f"Expected thinking for: {prompt!r}"
        else:
            assert thinking is None, f"Expected no thinking for: {prompt!r}"
        assert use_advisor == expected_advisor, f"Expected advisor={expected_advisor} for: {prompt!r}"
```

- [x] **Step 6: Update `select_model_with_overrides` to return 4 values**

Replace `select_model_with_overrides` (lines 122-156) with:

```python
async def select_model_with_overrides(
    message: str, conversation_context: list[dict] | None = None
) -> tuple[str, dict | None, str | None, bool]:
    """Route with learned overrides checked first.

    Returns (model, thinking_config, matched_rule, use_advisor).
    """
    msg_lower = message.lower().strip()

    # Check learned overrides first
    overrides = await load_overrides()
    for override in overrides:
        pattern = override["condition_pattern"]
        raw_pattern = pattern.split(":", 1)[1] if ":" in pattern else pattern
        try:
            if re.search(raw_pattern, msg_lower, re.IGNORECASE):
                thinking = None
                if override["thinking_mode"] == "adaptive":
                    thinking = THINKING_ADAPTIVE
                logger.debug(
                    "Router override matched: %s → %s (confidence=%.2f)",
                    pattern, override["preferred_model"], override["confidence"],
                )
                # Overrides don't use advisor — they are explicit model preferences
                return override["preferred_model"], thinking, pattern, False
        except re.error:
            continue

    # Fall back to standard routing (which now returns use_advisor)
    model, thinking, use_advisor = select_model(message, conversation_context)
    matched = _match_rule(message)
    if matched is None and conversation_context and _conversation_is_strategic(conversation_context):
        matched = "conversation_escalation"
    return model, thinking, matched, use_advisor
```

- [x] **Step 7: Update `TestSelectModelWithOverrides` tests**

Update all 4-value unpacking in the async test class:

```python
@pytest.mark.asyncio
class TestSelectModelWithOverrides:
    """Test that overrides layer works without breaking default routing."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        invalidate_overrides_cache()
        yield
        invalidate_overrides_cache()

    async def test_fallback_to_regex_when_no_overrides(self, monkeypatch):
        async def empty_overrides():
            return []
        monkeypatch.setattr("src.router.load_overrides", empty_overrides)

        model, thinking, rule, use_advisor = await select_model_with_overrides("What's on my calendar?")
        assert model == "claude-sonnet-4-6"
        assert thinking is None
        assert rule is not None
        assert rule.startswith("sonnet_override:")
        assert use_advisor is False

    async def test_override_takes_precedence(self, monkeypatch):
        async def fake_overrides():
            return [{
                "condition_pattern": "opus_signal:" + OPUS_SIGNALS[0],
                "preferred_model": "claude-sonnet-4-6",
                "thinking_mode": None,
                "confidence": 0.85,
            }]
        monkeypatch.setattr("src.router.load_overrides", fake_overrides)

        model, thinking, rule, use_advisor = await select_model_with_overrides("Let's discuss the strategy")
        assert model == "claude-sonnet-4-6"
        assert thinking is None
        assert "opus_signal:" in rule
        assert use_advisor is False  # Overrides don't use advisor

    async def test_override_with_adaptive_thinking(self, monkeypatch):
        async def fake_overrides():
            return [{
                "condition_pattern": r"moderate_signal:\b(compare|analyze)",
                "preferred_model": "claude-sonnet-4-6",
                "thinking_mode": "adaptive",
                "confidence": 0.75,
            }]
        monkeypatch.setattr("src.router.load_overrides", fake_overrides)

        model, thinking, rule, use_advisor = await select_model_with_overrides("Compare these options")
        assert model == "claude-sonnet-4-6"
        assert thinking == {"type": "adaptive"}
        assert use_advisor is False

    async def test_conversation_escalation_rule(self, monkeypatch):
        async def empty_overrides():
            return []
        monkeypatch.setattr("src.router.load_overrides", empty_overrides)

        context = [
            {"content": "strategy for Singapore"},
            {"content": "positioning with EDB"},
            {"content": "pre-mortem on the plan"},
            {"content": "what about implications?"},
        ]
        model, thinking, rule, use_advisor = await select_model_with_overrides("continue", context)
        assert model == "claude-sonnet-4-6"
        assert rule == "conversation_escalation"
        assert use_advisor is True
```

- [x] **Step 8: Run full router test suite**

Run: `cd /path/to/worktree/cos-agent && python3 -m pytest tests/test_router.py -v`
Expected: all tests PASS

- [x] **Step 9: Commit**

```bash
git add src/router.py tests/test_router.py
git commit -m "feat: router returns use_advisor flag, replaces Opus routing"
```

---

### Task 4: Failover — add advisor tool to beta API path

**Files:**
- Modify: `src/agent_failover.py`

- [x] **Step 1: Add `use_advisor` parameter and advisor tool injection**

Replace the `call_with_failover` function with:

```python
from config.settings import MODEL_FAILOVER_CHAIN, ADVISOR_MAX_USES

logger = logging.getLogger(__name__)

# Advisor tool definition (beta)
_ADVISOR_TOOL = {
    "type": "advisor_20260301",
    "name": "advisor",
    "model": "claude-opus-4-6",
    "max_uses": ADVISOR_MAX_USES,
}
_ADVISOR_BETA = "advisor-tool-2026-03-01"

# --- Circuit breaker (unchanged) ---
_consecutive_api_failures = 0
_CIRCUIT_BREAKER_THRESHOLD = 5
_circuit_breaker_alerted = False


async def call_with_failover(
    client: anthropic.Anthropic,
    model: str,
    system: list[dict],
    tools: list[dict],
    messages: list[dict],
    max_tokens: int | None = None,
    thinking: dict | None = None,
    use_advisor: bool = False,
) -> tuple[object, str]:
    """Try API call, cascading through failover models on 429/529 errors.

    Returns (response, model_actually_used) so cost tracking stays accurate.
    When use_advisor is True, injects the advisor tool and uses the beta API.
    Raises on unrecoverable errors (401 auth, 402 credits, persistent failures).
    """
    global _consecutive_api_failures

    # Build failover chain starting from the requested model
    try:
        start_idx = MODEL_FAILOVER_CHAIN.index(model)
        chain = MODEL_FAILOVER_CHAIN[start_idx:]
    except ValueError:
        chain = [model]

    last_error = None
    advisor_active = use_advisor  # May be disabled on failover
    for candidate in chain:
        try:
            # Extended thinking: only supported on Opus and Sonnet, not Haiku
            call_thinking = thinking if "haiku" not in candidate else None
            # Disable advisor on Haiku failover (advisor requires Sonnet+ executor)
            if "haiku" in candidate:
                advisor_active = False

            call_tools = list(tools)
            if advisor_active:
                call_tools.append(_ADVISOR_TOOL)

            call_kwargs = {
                "model": candidate,
                "max_tokens": max_tokens if max_tokens is not None else 4096,
                "system": system,
                "tools": call_tools,
                "messages": messages,
            }
            if call_thinking:
                call_kwargs["thinking"] = call_thinking

            if advisor_active:
                response = client.beta.messages.create(
                    betas=[_ADVISOR_BETA],
                    **call_kwargs,
                )
            else:
                response = client.messages.create(**call_kwargs)

            reset_circuit_breaker()
            if candidate != model:
                logger.info("Failover: responded on %s (requested %s)", candidate, model)
            return response, candidate
        except anthropic.APIError as e:
            error_msg = str(e)
            last_error = e
            _consecutive_api_failures += 1

            # Unrecoverable errors — fail immediately, don't try next model
            if "credit balance is too low" in error_msg:
                raise
            if "authentication" in error_msg.lower() or e.status_code == 401:
                raise

            # Retriable errors — try next model in chain
            if e.status_code in (429, 529) or "overloaded" in error_msg or "rate_limit" in error_msg:
                logger.warning(
                    "Failover: %s failed with %d, trying next model",
                    candidate, e.status_code,
                )
                continue

            # Unknown API error — try next model
            logger.warning("Failover: %s failed with %s, trying next", candidate, error_msg[:100])
            continue

    # All models exhausted — check circuit breaker
    if _consecutive_api_failures >= _CIRCUIT_BREAKER_THRESHOLD:
        await _notify_circuit_break(str(last_error)[:200] if last_error else "unknown")
    raise last_error  # type: ignore[misc]
```

- [x] **Step 2: Verify no syntax errors**

Run: `cd /path/to/worktree/cos-agent && python3 -c "from src.agent_failover import call_with_failover; print('OK')"`
Expected: `OK`

- [x] **Step 3: Commit**

```bash
git add src/agent_failover.py
git commit -m "feat: call_with_failover supports advisor tool via beta API"
```

---

### Task 5: Agent — wire advisor through the tool loop

**Files:**
- Modify: `src/agent.py`

- [x] **Step 1: Update model selection unpacking**

In `src/agent.py`, find the line (around line 697):
```python
        model, thinking, matched_rule = await select_model_with_overrides(user_message, history)
```
Replace with:
```python
        model, thinking, matched_rule, use_advisor = await select_model_with_overrides(user_message, history)
```

- [x] **Step 2: Update logging to include advisor status**

Find the log line (around line 702):
```python
    logger.info(
        "Processing message | model=%s | thinking=%s | mode=%s | history_len=%d | prompt_chars=%d",
        model,
        thinking["type"] if thinking else "off",
        "group" if group_mode else "dm",
        len(history),
        len(system_prompt),
    )
```
Replace with:
```python
    logger.info(
        "Processing message | model=%s | thinking=%s | advisor=%s | mode=%s | history_len=%d | prompt_chars=%d",
        model,
        thinking["type"] if thinking else "off",
        "on" if use_advisor else "off",
        "group" if group_mode else "dm",
        len(history),
        len(system_prompt),
    )
```

- [x] **Step 3: Pass `use_advisor` to `call_with_failover`**

Find the API call (around line 857):
```python
            response, model_used = await call_with_failover(
                client=client,
                model=model,
                system=system_with_cache,
                tools=tools_with_cache,
                messages=messages_with_cache,
                thinking=thinking,
                max_tokens=max_tokens,
            )
```
Replace with:
```python
            response, model_used = await call_with_failover(
                client=client,
                model=model,
                system=system_with_cache,
                tools=tools_with_cache,
                messages=messages_with_cache,
                thinking=thinking,
                max_tokens=max_tokens,
                use_advisor=use_advisor,
            )
```

- [x] **Step 4: Update cost tracking to handle advisor iterations**

Find the cost tracking block (around line 882):
```python
        # Track cost (including prompt cache and thinking tokens)
        call_cost = estimate_cost(
            model,
            response.usage.input_tokens,
            response.usage.output_tokens,
            cache_creation_tokens=getattr(response.usage, 'cache_creation_input_tokens', 0) or 0,
            cache_read_tokens=getattr(response.usage, 'cache_read_input_tokens', 0) or 0,
        )
        session_cost += call_cost
```
Replace with:
```python
        # Track cost (including prompt cache, thinking tokens, and advisor iterations)
        iterations = getattr(response.usage, 'iterations', None)
        if iterations:
            from src.cost_tracker import estimate_cost_with_advisor
            call_cost = estimate_cost_with_advisor(model, [
                {
                    "type": it.type,
                    "model": getattr(it, "model", None),
                    "input_tokens": getattr(it, "input_tokens", 0) or 0,
                    "output_tokens": getattr(it, "output_tokens", 0) or 0,
                    "cache_creation_input_tokens": getattr(it, "cache_creation_input_tokens", 0) or 0,
                    "cache_read_input_tokens": getattr(it, "cache_read_input_tokens", 0) or 0,
                }
                for it in iterations
            ])
        else:
            call_cost = estimate_cost(
                model,
                response.usage.input_tokens,
                response.usage.output_tokens,
                cache_creation_tokens=getattr(response.usage, 'cache_creation_input_tokens', 0) or 0,
                cache_read_tokens=getattr(response.usage, 'cache_read_input_tokens', 0) or 0,
            )
        session_cost += call_cost
```

- [x] **Step 5: Disable advisor after first iteration (same as thinking)**

Find the Opus downgrade block (around line 820):
```python
        # After the first iteration with Opus, downgrade to Sonnet for
        # tool-processing iterations (Sonnet handles mechanical tool loops fine
        # at 1/5th the cost). Opus does the initial strategic reasoning.
        if iteration > 1 and model == "claude-opus-4-6":
            model = "claude-sonnet-4-6"
            thinking = None  # Drop extended thinking for tool-loop iterations
            logger.info("Downgraded to Sonnet for tool-loop iteration %d", iteration)
            if model_callback:
                model_callback(model)
        # Drop thinking after first iteration even on Sonnet (thinking is for
        # initial reasoning, not mechanical tool processing)
        elif iteration > 1 and thinking:
            thinking = None
```
Replace with:
```python
        # After the first iteration with Opus, downgrade to Sonnet for
        # tool-processing iterations (Sonnet handles mechanical tool loops fine
        # at 1/5th the cost). Opus does the initial strategic reasoning.
        if iteration > 1 and model == "claude-opus-4-6":
            model = "claude-sonnet-4-6"
            thinking = None
            use_advisor = False
            logger.info("Downgraded to Sonnet for tool-loop iteration %d", iteration)
            if model_callback:
                model_callback(model)
        # Drop thinking and advisor after first iteration (strategic reasoning
        # is for the first turn, tool-loop iterations are mechanical)
        elif iteration > 1:
            if thinking:
                thinking = None
            if use_advisor:
                use_advisor = False
                logger.info("Advisor disabled for tool-loop iteration %d", iteration)
```

- [x] **Step 6: Strip advisor blocks from history when advisor is off**

Find `_prune_old_tool_results` (around line 486). Add a new helper function right before it:

```python
_ADVISOR_BLOCK_TYPES = {"server_tool_use", "advisor_tool_result"}


def _strip_advisor_blocks(messages: list[dict]) -> list[dict]:
    """Remove server_tool_use and advisor_tool_result blocks from message history.

    Required when the current turn doesn't use the advisor tool but history
    contains advisor blocks from previous turns — the API returns 400 otherwise.
    """
    stripped = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            stripped.append(msg)
            continue
        # Filter out advisor-related blocks
        filtered = [
            block for block in content
            if not (
                isinstance(block, dict) and block.get("type") in _ADVISOR_BLOCK_TYPES
                or hasattr(block, "type") and block.type in _ADVISOR_BLOCK_TYPES
            )
        ]
        if filtered != content:
            stripped.append({**msg, "content": filtered if filtered else "[Advisor context removed]"})
        else:
            stripped.append(msg)
    return stripped
```

Then in the tool loop, right before the API call (around where `messages_with_cache` is built), add advisor block stripping when advisor is off. Find:
```python
            # Mark the last message with cache_control to cache conversation prefix
            messages_with_cache = _add_cache_to_last_message(messages)
```
Replace with:
```python
            # Strip advisor blocks from history if advisor is off this iteration
            messages_for_call = _strip_advisor_blocks(messages) if not use_advisor else messages
            # Mark the last message with cache_control to cache conversation prefix
            messages_with_cache = _add_cache_to_last_message(messages_for_call)
```

- [x] **Step 7: Verify no syntax errors**

Run: `cd /path/to/worktree/cos-agent && python3 -c "from src.agent import process_message; print('OK')"`
Expected: `OK`

- [x] **Step 8: Commit**

```bash
git add src/agent.py
git commit -m "feat: wire advisor tool through agent loop with cost tracking"
```

---

### Task 6: Agent tests — advisor block stripping

**Files:**
- Modify: `tests/test_agent.py`

- [x] **Step 1: Write failing test for `_strip_advisor_blocks`**

Add to `tests/test_agent.py` imports:
```python
from src.agent import _strip_advisor_blocks
```

Add test class:

```python
class TestStripAdvisorBlocks:
    def test_strips_server_tool_use_and_advisor_result(self):
        messages = [
            {"role": "user", "content": "What's the strategy?"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "Let me consult the advisor."},
                {"type": "server_tool_use", "id": "srvtoolu_123", "name": "advisor", "input": {}},
                {"type": "advisor_tool_result", "tool_use_id": "srvtoolu_123",
                 "content": {"type": "advisor_result", "text": "Here is my advice..."}},
                {"type": "text", "text": "Based on the advice, here's what I think."},
            ]},
        ]
        result = _strip_advisor_blocks(messages)
        assert result[0] == messages[0]  # User message unchanged
        assistant_content = result[1]["content"]
        types = [b["type"] for b in assistant_content]
        assert "server_tool_use" not in types
        assert "advisor_tool_result" not in types
        assert types == ["text", "text"]

    def test_no_advisor_blocks_unchanged(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "hi there"},
            ]},
        ]
        result = _strip_advisor_blocks(messages)
        assert result == messages

    def test_string_content_unchanged(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "plain string response"},
        ]
        result = _strip_advisor_blocks(messages)
        assert result == messages

    def test_all_advisor_blocks_replaced_with_placeholder(self):
        messages = [
            {"role": "assistant", "content": [
                {"type": "server_tool_use", "id": "srvtoolu_123", "name": "advisor", "input": {}},
                {"type": "advisor_tool_result", "tool_use_id": "srvtoolu_123",
                 "content": {"type": "advisor_result", "text": "advice"}},
            ]},
        ]
        result = _strip_advisor_blocks(messages)
        assert result[0]["content"] == "[Advisor context removed]"
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /path/to/worktree/cos-agent && python3 -m pytest tests/test_agent.py::TestStripAdvisorBlocks -v`
Expected: FAIL with `ImportError`

- [x] **Step 3: Run test to verify it passes** (implementation was done in Task 5)

Run: `cd /path/to/worktree/cos-agent && python3 -m pytest tests/test_agent.py::TestStripAdvisorBlocks -v`
Expected: all 4 PASS

- [x] **Step 4: Run full test suite**

Run: `cd /path/to/worktree/cos-agent && python3 -m pytest -v`
Expected: all tests PASS

- [x] **Step 5: Commit**

```bash
git add tests/test_agent.py
git commit -m "test: add advisor block stripping tests"
```

---

### Task 7: Final verification and cleanup

- [x] **Step 1: Run full test suite**

Run: `cd /path/to/worktree/cos-agent && python3 -m pytest -v`
Expected: all tests PASS, no regressions

- [x] **Step 2: Verify imports are clean**

Run: `cd /path/to/worktree/cos-agent && python3 -c "from src.agent import process_message; from src.router import select_model, select_model_with_overrides; from src.agent_failover import call_with_failover; from src.cost_tracker import estimate_cost_with_advisor; print('All imports OK')"`
Expected: `All imports OK`

- [x] **Step 3: Push and create PR**

```bash
git push -u origin feat/advisor-tool
gh pr create --title "feat: advisor tool integration" --body "..."
```
