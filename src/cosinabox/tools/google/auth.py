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


def build_all_credentials() -> list[Credentials]:
    """Build credentials for all configured Google accounts.

    Looks for GOOGLE_OAUTH_REFRESH_TOKEN_1, _2, _3, etc.
    Falls back to single GOOGLE_OAUTH_REFRESH_TOKEN if no numbered ones found.
    """
    cid = os.getenv("GOOGLE_OAUTH_CLIENT_ID")
    secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")
    if not cid or not secret:
        raise GoogleAuthError("GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET required.")

    tokens: list[str] = []
    i = 1
    while True:
        tok = os.getenv(f"GOOGLE_OAUTH_REFRESH_TOKEN_{i}")
        if tok is None:
            break
        tokens.append(tok)
        i += 1

    if not tokens:
        single = os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN")
        if single:
            tokens.append(single)

    if not tokens:
        raise GoogleAuthError("No GOOGLE_OAUTH_REFRESH_TOKEN found.")

    return [
        Credentials(  # type: ignore[no-untyped-call]
            token=None,
            refresh_token=tok,
            token_uri=GOOGLE_TOKEN_URI,
            client_id=cid,
            client_secret=secret,
            scopes=list(GOOGLE_DEFAULT_SCOPES),
        )
        for tok in tokens
    ]
