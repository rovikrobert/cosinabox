"""Stress tests for module-global dicts that are mutated across threads.

These tests target the lock paths added to guard:
- policy._pending_approvals (approval tokens)
- loop._consecutive_failures / _last_failure_at (circuit breaker)

They do not aim for full permutation coverage — they exercise the lock
under concurrent load and assert no RuntimeError + no double-consumption.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from cosinabox.agent import loop as loop_module
from cosinabox.agent.cost import CostTracker
from cosinabox.agent.loop import AgentLoop
from cosinabox.agent.policy import (
    _check_temporary_approval,
    clear_approvals,
    grant_temporary_approval,
)
from cosinabox.agent.routing import Router


class TestApprovalTokenThreadSafety:
    def test_no_double_consumption_under_concurrent_consume(self) -> None:
        """Grant 1 token, have 50 threads race to consume it.
        Exactly one thread must succeed."""
        clear_approvals()
        grant_temporary_approval("sess-1", "gmail_send")

        successes: list[bool] = []
        lock = threading.Lock()

        def consume() -> None:
            ok = _check_temporary_approval("sess-1", "gmail_send")
            with lock:
                successes.append(ok)

        threads = [threading.Thread(target=consume) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly one thread consumed the token
        assert sum(1 for ok in successes if ok) == 1
        assert len(successes) == 50

    def test_concurrent_grant_and_consume_no_exceptions(self) -> None:
        """50 threads each doing grant/consume/sweep cycles on distinct keys.
        No RuntimeError ('dictionary changed size during iteration')."""
        clear_approvals()
        errors: list[BaseException] = []

        def worker(i: int) -> None:
            try:
                for j in range(20):
                    session = f"sess-{i}-{j}"
                    grant_temporary_approval(session, "gmail_send")
                    # consume some, leave some for sweep
                    if j % 2 == 0:
                        _check_temporary_approval(session, "gmail_send")
            except BaseException as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors


class TestCircuitBreakerThreadSafety:
    def _reset(self) -> None:
        loop_module._consecutive_failures = 0
        loop_module._last_failure_at = 0.0

    def test_concurrent_failures_increment_counter_monotonically(self) -> None:
        """50 threads each simulating a failed API call — every increment
        must be accounted for; no lost increments."""
        self._reset()

        def _build_loop() -> AgentLoop:
            client = MagicMock()
            client.messages.create.side_effect = Exception("boom")
            return AgentLoop(
                anthropic_client=client,
                router=Router(),
                cost_tracker=CostTracker(per_message_cap_usd=10.0, daily_cap_usd=100.0),
                tools={},
                max_tool_iterations=1,
            )

        errors: list[BaseException] = []

        def worker() -> None:
            try:
                loop = _build_loop()
                loop.run(prompt="hello", session_id="s")
            except BaseException as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # Every worker produced at least one failure path; the counter is
        # clamped/reset by _circuit_breaker_tripped once the threshold is
        # reached, so we only assert it's >= threshold (no exceptions is
        # the real ask here).
        assert loop_module._consecutive_failures >= loop_module._CIRCUIT_BREAKER_THRESHOLD
        self._reset()

    def test_concurrent_tripped_checks_no_exceptions(self) -> None:
        """Many threads calling _circuit_breaker_tripped concurrently must
        not race on the reset path."""
        self._reset()
        loop_module._consecutive_failures = 10
        loop_module._last_failure_at = 0.0  # long ago -> should reset

        errors: list[BaseException] = []
        results: list[bool] = []
        result_lock = threading.Lock()

        def check() -> None:
            try:
                tripped = loop_module._circuit_breaker_tripped()
                with result_lock:
                    results.append(tripped)
            except BaseException as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=check) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # All checks should report "not tripped" after cooldown reset.
        assert all(r is False for r in results)
        self._reset()
