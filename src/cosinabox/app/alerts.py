"""Telegram output wiring — send_telegram factory, auth-error alert, job wrapping."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from cosinabox.jobs.base import JobContext
from cosinabox.scheduler.runner import SchedulerRunner

logger = logging.getLogger("cosinabox")


def make_send_telegram(bot_token: str, chat_id: str) -> Callable[[str], None]:
    """Create a send_telegram closure that posts to the Telegram API."""
    import httpx

    tg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send_telegram(text: str) -> None:
        for i in range(0, len(text), 4000):
            httpx.post(
                tg_url,
                json={"chat_id": chat_id, "text": text[i : i + 4000]},
            )

    return send_telegram


def send_auth_error_alert(
    send_fn: Callable[[str], None],
    auth_errors: list[str],
) -> None:
    """Surface auth / tool init failures via Telegram.

    Per feedback_flag_oauth_failures: never silently drop accounts.
    """
    if not auth_errors:
        return
    alert_body = "\n\n".join(f"- {e}" for e in auth_errors)
    try:
        send_fn(f"[cosinabox startup] Integration auth issues detected:\n\n{alert_body}")
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send auth-error alert via Telegram")


def wire_telegram_output(scheduler: SchedulerRunner, send_fn: Any) -> None:
    """Wrap each job's run() to send output to Telegram."""
    NO_OP = ("no upcoming", "no events", "no meetings", "(no ")

    for jname, registered_job in scheduler._jobs.items():
        orig = registered_job.run

        def _wrap(original: Any, name: str) -> Any:
            def wrapped(ctx: JobContext | None = None) -> str:
                result: str = original(ctx or JobContext())
                if not result or not result.strip():
                    return result
                if any(m in result.lower() for m in NO_OP):
                    return result
                try:
                    send_fn(f"[{name}]\n\n{result}")
                except Exception:
                    logger.exception("Telegram send failed for %s", name)
                return result

            return wrapped

        registered_job.run = _wrap(orig, jname)  # type: ignore[method-assign]  # monkey-patching for telegram output
