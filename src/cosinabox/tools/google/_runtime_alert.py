"""Runtime OAuth failure alerting — shared by Calendar and Gmail tools.

Sends a one-shot Telegram alert when a Google token expires at runtime,
then suppresses further alerts until the service restarts (or a cooldown
elapses). This fills the gap left by startup-only alerting (PR #22 item 3).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Deduplicate alerts: only alert once per cooldown window (1 hour).
_ALERT_COOLDOWN_S = 3600
_last_alert_at: float = 0.0
_alert_lock = threading.Lock()

# Optional send_telegram callback — set by the app layer at startup.
# If not set, we log a warning instead.
_send_telegram_fn: Callable[[str], None] | None = None


def set_send_telegram(fn: Callable[[str], None]) -> None:
    """Register the send_telegram callback (called once by App at startup)."""
    global _send_telegram_fn
    _send_telegram_fn = fn


def runtime_oauth_alert(exc: Exception) -> None:
    """Send a Telegram alert for a runtime Google OAuth failure.

    Deduplicates: only sends once per cooldown window.
    """
    global _last_alert_at
    with _alert_lock:
        now = time.time()
        if now - _last_alert_at < _ALERT_COOLDOWN_S:
            return
        _last_alert_at = now

    msg = f"[auth] Google OAuth token expired. Run: cosinabox auth google\n\nError: {exc}"
    if _send_telegram_fn is not None:
        try:
            _send_telegram_fn(msg)
        except Exception:
            logger.exception("Failed to send runtime OAuth alert via Telegram")
    else:
        logger.warning("Runtime OAuth alert (no Telegram configured): %s", msg)
