"""Auth-health watcher — flag revoked Google refresh tokens before they're noticed by a human.

Runs on a scheduler cadence (default every 15 min). On each tick, attempts to
refresh every configured Google credential and emits a Telegram alert when an
account transitions between healthy and unhealthy. State lives in-memory per
process — on restart, still-broken accounts alert again on the first tick (by
design: a restart is a useful re-prompt).

See docs/specs/2026-04-17-auth-health-watcher-design.md for the full design.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from typing import Any

from cosinabox.jobs.base import Job, JobContext
from cosinabox.tools.google.auth import GoogleAuthError, build_all_credentials

logger = logging.getLogger("cosinabox")

_FAILURE_TEMPLATE = (
    "Google auth failed for account #{i}.\n"
    "Gmail and Calendar reads will be silently skipped until re-auth.\n"
    "Fix: `cosinabox auth google`, update GOOGLE_OAUTH_REFRESH_TOKEN_{i} on "
    "Railway, redeploy."
)
_RECOVERY_TEMPLATE = "Google auth restored for account #{i}."


class AuthHealthJob(Job):
    name = "auth_health"

    def __init__(
        self,
        *,
        credentials_factory: Callable[[], Iterable[Any]] = build_all_credentials,
    ) -> None:
        self.credentials_factory = credentials_factory
        self._health: dict[int, bool] = {}

    def run(self, context: JobContext) -> str:
        try:
            creds = list(self.credentials_factory())
        except GoogleAuthError:
            return ""

        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request

        request = Request()
        newly_failed: list[str] = []
        newly_recovered: list[str] = []

        for i, cred in enumerate(creds, start=1):
            ok: bool
            try:
                cred.refresh(request)
                ok = True
            except RefreshError as exc:
                logger.warning("Auth-health: account #%d refresh failed: %s", i, exc)
                ok = False
            except Exception as exc:  # noqa: BLE001 — preserve state on transient failures
                logger.warning(
                    "Auth-health: account #%d raised %s; keeping prior state",
                    i,
                    type(exc).__name__,
                )
                continue

            prev = self._health.get(i)
            if ok is False and prev is not False:
                newly_failed.append(_FAILURE_TEMPLATE.format(i=i))
            elif ok is True and prev is False:
                newly_recovered.append(_RECOVERY_TEMPLATE.format(i=i))
            self._health[i] = ok

        sections: list[str] = []
        if newly_failed:
            sections.append("\n".join(newly_failed))
        if newly_recovered:
            sections.append("\n".join(newly_recovered))
        return "\n\n".join(sections)
