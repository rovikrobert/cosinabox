from __future__ import annotations

import os
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
