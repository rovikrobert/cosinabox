"""Scheduler lifecycle hooks: install signal handlers, graceful shutdown."""

from __future__ import annotations

import signal
from collections.abc import Callable


def install_shutdown_handler(shutdown: Callable[[], None]) -> None:
    def _handler(signum: int, frame: object) -> None:  # noqa: ARG001
        shutdown()

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
