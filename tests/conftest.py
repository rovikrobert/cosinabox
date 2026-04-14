"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    from cosinabox.agent import loop as loop_module

    loop_module._consecutive_failures = 0
    loop_module._last_failure_at = 0.0
    yield
    loop_module._consecutive_failures = 0
    loop_module._last_failure_at = 0.0
