"""Google OAuth helper — single-account default."""

from __future__ import annotations

import os

try:
    from google.oauth2.credentials import Credentials
except ImportError as e:
    raise ImportError(
        "cosinabox[google] extra is required. Run: pip install 'cosinabox[google]'"
    ) from e

GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_DEFAULT_SCOPES = (
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
)


class GoogleAuthError(Exception):
    pass


def build_credentials() -> Credentials:
    cid = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    refresh = os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN")
    missing = [
        n
        for n, v in (
            ("GOOGLE_OAUTH_CLIENT_ID", cid),
            ("GOOGLE_OAUTH_CLIENT_SECRET", secret),
            ("GOOGLE_OAUTH_REFRESH_TOKEN", refresh),
        )
        if not v
    ]
    if missing:
        raise GoogleAuthError(
            f"Missing required env vars: {', '.join(missing)}. "
            "Run `cosinabox auth google` to mint a refresh token."
        )
    return Credentials(  # type: ignore[no-untyped-call]
        token=None,
        refresh_token=refresh,
        token_uri=GOOGLE_TOKEN_URI,
        client_id=cid,
        client_secret=secret,
        scopes=list(GOOGLE_DEFAULT_SCOPES),
    )
