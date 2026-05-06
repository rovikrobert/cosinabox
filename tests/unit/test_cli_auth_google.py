from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from cosinabox.cli.main import cli


def test_auth_google_prints_refresh_token() -> None:
    fake_flow = MagicMock()
    fake_creds = MagicMock(refresh_token="r-token-1")
    fake_flow.run_local_server.return_value = fake_creds
    with (
        patch.dict(
            os.environ,
            {"GOOGLE_OAUTH_CLIENT_ID": "cid", "GOOGLE_OAUTH_CLIENT_SECRET": "sec"},
            clear=True,
        ),
        patch(
            "cosinabox.cli.auth_google.InstalledAppFlow.from_client_config", return_value=fake_flow
        ),
    ):
        runner = CliRunner()
        result = runner.invoke(cli, ["auth", "google"])
    assert result.exit_code == 0
    assert "r-token-1" in result.output


def test_auth_google_errors_without_env() -> None:
    env_without_google = {
        k: v
        for k, v in os.environ.items()
        if k not in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET")
    }
    with patch.dict(os.environ, env_without_google, clear=True):
        runner = CliRunner()
        result = runner.invoke(cli, ["auth", "google"])
    assert result.exit_code != 0


# --- multi-account safety: --account flag ---
#
# A multi-account user (e.g. rovik-keevs runs two Google accounts) can
# accidentally re-auth the wrong inbox if their browser is logged in as a
# different account at consent time. The flow succeeds, prints a token, the
# user pastes it into REFRESH_TOKEN_2 — and auth_health keeps flagging
# account #2 because the token is for a different inbox. --account makes
# this a hard error instead of silent corruption.


def _invoke_with_consent(consented_email: str, args: list[str]) -> Any:
    """Run `auth google` with the OAuth flow stubbed to a fixed consented email."""
    fake_flow = MagicMock()
    fake_creds = MagicMock(refresh_token="rt-test")
    fake_flow.run_local_server.return_value = fake_creds
    with (
        patch.dict(
            os.environ,
            {"GOOGLE_OAUTH_CLIENT_ID": "cid", "GOOGLE_OAUTH_CLIENT_SECRET": "sec"},
            clear=True,
        ),
        patch(
            "cosinabox.cli.auth_google.InstalledAppFlow.from_client_config",
            return_value=fake_flow,
        ),
        patch(
            "cosinabox.cli.auth_google._consented_email",
            return_value=consented_email,
        ),
    ):
        return CliRunner().invoke(cli, ["auth", "google", *args])


def test_auth_google_account_match_prints_token() -> None:
    result = _invoke_with_consent("rovik@cantina.ai", ["--account", "rovik@cantina.ai"])
    assert result.exit_code == 0
    assert "rt-test" in result.output


def test_auth_google_account_mismatch_refuses_to_print() -> None:
    result = _invoke_with_consent("rovikjeremiah@gmail.com", ["--account", "rovik@cantina.ai"])
    assert result.exit_code != 0
    # Both emails should appear so the user can see what went wrong.
    assert "rovikjeremiah@gmail.com" in result.output
    assert "rovik@cantina.ai" in result.output
    # The token must NOT leak — that's the whole point of this guard.
    assert "rt-test" not in result.output


def test_auth_google_account_match_is_case_insensitive() -> None:
    result = _invoke_with_consent("Rovik@Cantina.AI", ["--account", "rovik@cantina.ai"])
    assert result.exit_code == 0
    assert "rt-test" in result.output
