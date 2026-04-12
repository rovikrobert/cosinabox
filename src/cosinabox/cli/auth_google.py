"""`cosinabox auth google` — OAuth flow to obtain Google refresh token."""

from __future__ import annotations

import os

import click

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    InstalledAppFlow = None  # type: ignore[assignment,unused-ignore]

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
]


@click.group("auth")
def auth_cmd() -> None:
    """Authentication helpers."""


@auth_cmd.command("google")
def auth_google_cmd() -> None:
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

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=_SCOPES)
    creds = flow.run_local_server(port=0)
    click.echo(f"Refresh token: {creds.refresh_token}")
