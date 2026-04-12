from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from cosinabox.tools.google.auth import (
    GoogleAuthError,
    build_credentials,
)


def test_missing_env_raises() -> None:
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(GoogleAuthError, match="GOOGLE_OAUTH_CLIENT_ID"):
            build_credentials()


def test_env_present_returns_credentials() -> None:
    env = {
        "GOOGLE_OAUTH_CLIENT_ID": "cid",
        "GOOGLE_OAUTH_CLIENT_SECRET": "secret",
        "GOOGLE_OAUTH_REFRESH_TOKEN": "rtoken",
    }
    with patch.dict(os.environ, env, clear=True):
        with patch("cosinabox.tools.google.auth.Credentials") as MockCreds:
            instance = MagicMock()
            MockCreds.return_value = instance
            creds = build_credentials()
            assert creds is instance
            MockCreds.assert_called_once()
            kwargs = MockCreds.call_args.kwargs
            assert kwargs["client_id"] == "cid"
            assert kwargs["client_secret"] == "secret"
            assert kwargs["refresh_token"] == "rtoken"
