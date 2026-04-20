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
# Note: `drive.readonly` is requested but not enforced — existing refresh
# tokens minted before this scope landed will keep working for Gmail +
# Calendar; Drive API calls just 403 and the DriveTool catches it.
# Users who want Drive search run `cosinabox auth google` to re-mint.
GOOGLE_DEFAULT_SCOPES = (
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive.readonly",
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


def build_all_credentials() -> list[Credentials]:
    """Build credentials for all numbered GOOGLE_OAUTH_REFRESH_TOKEN_N env vars.

    Scans GOOGLE_OAUTH_REFRESH_TOKEN_1, _2, _3 etc. Falls back to single
    GOOGLE_OAUTH_REFRESH_TOKEN if no numbered tokens are found.
    """
    cid = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    if not cid or not secret:
        raise GoogleAuthError(
            "Missing GOOGLE_OAUTH_CLIENT_ID or GOOGLE_OAUTH_CLIENT_SECRET. "
            "Run `cosinabox auth google` to configure."
        )

    creds: list[Credentials] = []
    for i in range(1, 10):
        token = os.getenv(f"GOOGLE_OAUTH_REFRESH_TOKEN_{i}")
        if not token:
            break
        creds.append(
            Credentials(  # type: ignore[no-untyped-call]
                token=None,
                refresh_token=token,
                token_uri=GOOGLE_TOKEN_URI,
                client_id=cid,
                client_secret=secret,
                scopes=list(GOOGLE_DEFAULT_SCOPES),
            )
        )

    if not creds:
        # Fall back to single token
        creds.append(build_credentials())

    return creds
