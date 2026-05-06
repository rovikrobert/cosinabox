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
from pathlib import Path
from typing import Any

from cosinabox.jobs.base import Job, JobContext
from cosinabox.tools.google.auth import GoogleAuthError, build_all_credentials

logger = logging.getLogger("cosinabox")

# After Initiative A (`cosinabox auth refresh`) shipped in v0.1.6, the fix
# instruction collapses from a three-step manual flow (auth google + update
# GOOGLE_OAUTH_REFRESH_TOKEN_<N> on Railway + redeploy) to a single command.
# Surfaces that still referenced the old text were updated in lockstep.
_FAILURE_TEMPLATE = (
    "Google auth failed for account #{i}.\n"
    "Gmail and Calendar reads will be silently skipped until re-auth.\n"
    "Run: cosinabox auth refresh"
)
_RECOVERY_TEMPLATE = "Google auth restored for account #{i}."


class AuthHealthJob(Job):
    name = "auth_health"

    def __init__(
        self,
        *,
        credentials_factory: Callable[[], Iterable[Any]] = build_all_credentials,
        db_path: Path | None = None,
        account_emails: list[str] | None = None,
    ) -> None:
        """Args:
        credentials_factory: callable returning the list of Credentials
            to probe each tick. Defaults to ``build_all_credentials``.
        db_path: path to the user repo's ``memory.db``. When provided,
            each tick persists per-account status to the
            ``auth_health_status`` table for ``/status`` to read.
            Optional so existing callers (and most tests) don't need
            to thread it.
        account_emails: ordered list of emails matching the credentials
            returned by the factory. Used as the email field in
            persisted rows. When None, falls back to ``"(unknown)"`` so
            persistence still works.
        """
        self.credentials_factory = credentials_factory
        self.db_path = db_path
        self.account_emails = list(account_emails or [])
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
                # Skip the persistence write below so the prior known
                # status survives the network blip — same semantic as
                # the in-memory _health dict.
                continue

            prev = self._health.get(i)
            if ok is False and prev is not False:
                newly_failed.append(_FAILURE_TEMPLATE.format(i=i))
            elif ok is True and prev is False:
                newly_recovered.append(_RECOVERY_TEMPLATE.format(i=i))
            self._health[i] = ok

            if self.db_path is not None:
                from cosinabox.jobs.auth_health_persist import record_auth_health

                email = (
                    self.account_emails[i - 1] if 0 < i <= len(self.account_emails) else "(unknown)"
                )
                try:
                    record_auth_health(self.db_path, account_index=i, email=email, ok=ok)
                except Exception:  # noqa: BLE001 — persistence must never break the watcher
                    logger.warning(
                        "Auth-health: failed to persist account #%d state",
                        i,
                        exc_info=True,
                    )

        sections: list[str] = []
        if newly_failed:
            sections.append("\n".join(newly_failed))
        if newly_recovered:
            sections.append("\n".join(newly_recovered))
        return "\n\n".join(sections)
