"""In-memory hourly rate limiter for the consult MCP endpoint.

One instance per process. Wall-clock-based (not monotonic) so a server
restart resets the window — acceptable for a shared-secret endpoint where
the primary threat model is "external client loop runs away," not an
adversary trying to circumvent the limit by restarting the server.

Defaults live in `cosinabox.defaults.CONSULT_RATE_LIMIT_PER_HOUR`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class RateLimiter:
    """Sliding-window-ish hourly counter.

    Semantics:
      * `limit` requests allowed per `window_seconds` (default: 3600s).
      * When `allow()` is called after `window_seconds` has elapsed since
        `window_start`, the counter resets to 0 and the window restarts.
      * Otherwise, `allow()` increments the counter and returns True until
        `count >= limit`, at which point it returns False without advancing
        the counter further (so a denied request does not push the next
        window's start time forward).
    """

    limit: int
    count: int = 0
    window_start: float = 0.0
    window_seconds: int = 3600

    def allow(self) -> bool:
        now = time.time()
        if now - self.window_start >= self.window_seconds:
            self.count = 0
            self.window_start = now
        if self.count >= self.limit:
            return False
        self.count += 1
        return True

    def snapshot(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "limit": self.limit,
            "window_start": self.window_start,
        }


_default: RateLimiter | None = None


def get_default_rate_limiter() -> RateLimiter:
    """Return (and lazily construct) the process-wide rate limiter singleton."""
    global _default
    if _default is None:
        # Imported lazily so a consumer importing this module without ever
        # calling the accessor doesn't pay for defaults module import.
        from cosinabox import defaults

        _default = RateLimiter(
            limit=defaults.CONSULT_RATE_LIMIT_PER_HOUR,
            window_start=time.time(),
        )
    return _default


def reset_default_rate_limiter() -> None:
    """Test hook — drops the singleton so the next `get_default_rate_limiter()`
    call rebuilds a fresh instance anchored at the current wall-clock."""
    global _default
    _default = None
