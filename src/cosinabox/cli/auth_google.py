"""`cosinabox auth google` — OAuth flow to obtain Google refresh token."""

from __future__ import annotations

import os
from typing import Any

import click

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    InstalledAppFlow = None

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]


def _consented_email(creds: Any) -> str | None:
    """Return the email of the Google account that completed consent.

    Calls Google's userinfo endpoint with the freshly-minted credentials.
    Returns None on any failure (network, missing scope) — caller treats
    that as "couldn't verify" and refuses to print under --account.
    """
    try:
        from googleapiclient.discovery import build  # type: ignore[import-untyped]

        svc = build("oauth2", "v2", credentials=creds, cache_discovery=False)
        info = svc.userinfo().get().execute()
    except Exception:  # noqa: BLE001 — best-effort verification
        return None
    email = info.get("email") if isinstance(info, dict) else None
    return str(email) if email else None


@click.group("auth")
def auth_cmd() -> None:
    """Authentication helpers."""


@auth_cmd.command("google")
@click.option(
    "--account",
    "expected_email",
    default=None,
    help=(
        "Email of the Google account this token is FOR. If the consent "
        "screen completes with a different account, the flow refuses to "
        "print the token. Use this for multi-account setups so a stray "
        "browser session can't silently mint a token for the wrong inbox."
    ),
)
def auth_google_cmd(expected_email: str | None) -> None:
    """Run Google OAuth flow and print the refresh token."""
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise click.ClickException(
            "GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be set."
        )

    if InstalledAppFlow is None:
        raise click.ClickException(
            "google-auth-oauthlib is not installed. Run: pip install google-auth-oauthlib"
        )

    # Add openid + email scopes when --account is requested so the userinfo
    # lookup works. Additive — callers without --account get the original
    # two scopes and no behaviour change.
    scopes = list(_SCOPES)
    if expected_email is not None:
        scopes.extend(
            [
                "openid",
                "https://www.googleapis.com/auth/userinfo.email",
            ]
        )

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=scopes)
    creds = flow.run_local_server(port=0)

    if expected_email is not None:
        consented = _consented_email(creds)
        if consented is None:
            raise click.ClickException(
                "Could not verify which account completed consent — refusing "
                f"to print a refresh token for --account {expected_email}. "
                "Re-run without --account to skip the check."
            )
        if consented.lower() != expected_email.lower():
            raise click.ClickException(
                f"Consent screen completed with {consented}, not "
                f"{expected_email}. Refusing to print the token — it would "
                "be for the wrong inbox. Sign out of the wrong account in "
                "your browser (or use a private window) and re-run."
            )

    click.echo(f"Refresh token: {creds.refresh_token}")
