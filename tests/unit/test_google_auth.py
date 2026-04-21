from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from cosinabox.tools.google.auth import (
    GoogleAuthError,
    build_all_credentials,
    build_credentials,
)


def test_missing_env_raises() -> None:
    with (
        patch.dict(os.environ, {}, clear=True),
        pytest.raises(GoogleAuthError, match="GOOGLE_OAUTH_CLIENT_ID"),
    ):
        build_credentials()


def test_env_present_returns_credentials() -> None:
    env = {
        "GOOGLE_OAUTH_CLIENT_ID": "cid",
        "GOOGLE_OAUTH_CLIENT_SECRET": "secret",
        "GOOGLE_OAUTH_REFRESH_TOKEN": "rtoken",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("cosinabox.tools.google.auth.Credentials") as MockCreds,
    ):
        instance = MagicMock()
        MockCreds.return_value = instance
        creds = build_credentials()
        assert creds is instance
        MockCreds.assert_called_once()
        kwargs = MockCreds.call_args.kwargs
        assert kwargs["client_id"] == "cid"
        assert kwargs["client_secret"] == "secret"
        assert kwargs["refresh_token"] == "rtoken"


def test_build_credentials_does_not_pass_scopes() -> None:
    """Credentials must be built WITHOUT the scopes= kwarg.

    google-auth sends scopes on refresh. When a refresh token was minted
    with narrower scopes than GOOGLE_DEFAULT_SCOPES (e.g. pre-drive.readonly
    tokens), Google rejects the refresh with `invalid_scope: Bad Request`
    — breaking Gmail and Calendar, not just Drive. Inheriting the
    original grant's scopes (by omitting the kwarg) keeps old tokens
    working; Drive API calls just 403 which the DriveTool catches.
    """
    env = {
        "GOOGLE_OAUTH_CLIENT_ID": "cid",
        "GOOGLE_OAUTH_CLIENT_SECRET": "secret",
        "GOOGLE_OAUTH_REFRESH_TOKEN": "rtoken",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("cosinabox.tools.google.auth.Credentials") as MockCreds,
    ):
        build_credentials()
        assert "scopes" not in MockCreds.call_args.kwargs, (
            "build_credentials must not pass scopes= — forces over-request "
            "on refresh for pre-drive tokens"
        )


def test_build_all_credentials_does_not_pass_scopes() -> None:
    """Same contract for the multi-account builder."""
    env = {
        "GOOGLE_OAUTH_CLIENT_ID": "cid",
        "GOOGLE_OAUTH_CLIENT_SECRET": "secret",
        "GOOGLE_OAUTH_REFRESH_TOKEN_1": "rtoken1",
        "GOOGLE_OAUTH_REFRESH_TOKEN_2": "rtoken2",
    }
    with (
        patch.dict(os.environ, env, clear=True),
        patch("cosinabox.tools.google.auth.Credentials") as MockCreds,
    ):
        build_all_credentials()
        assert MockCreds.call_count == 2
        for call in MockCreds.call_args_list:
            assert "scopes" not in call.kwargs, (
                "build_all_credentials must not pass scopes= for any account"
            )
