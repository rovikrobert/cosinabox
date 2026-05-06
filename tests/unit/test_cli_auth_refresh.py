"""Tests for `cosinabox auth refresh`.

All Railway CLI calls and the OAuth consent flow are mocked. These
tests verify orchestration logic, not the real Railway CLI or Google
OAuth (those are tested independently in their own modules).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml
from click.testing import CliRunner

from cosinabox.cli.main import cli


def _write_integrations(tmp_path: Path, accounts: list[dict[str, str]]) -> Path:
    cfg = {
        "schema_version": 1,
        "integrations": {"google": {"enabled": True, "accounts": accounts}},
    }
    (tmp_path / "integrations.yaml").write_text(yaml.safe_dump(cfg))
    return tmp_path


def test_auth_refresh_happy_path_single_account(tmp_path: Path) -> None:
    """Single-account user → no picker → mint → set _1 → redeploy → SUCCESS."""
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])

    set_calls: list[tuple[str, str]] = []

    with (
        patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=True),
        patch(
            "cosinabox.cli.auth_refresh._railway.whoami",
            return_value="rovik@example.com",
        ),
        patch(
            "cosinabox.cli.auth_refresh._railway.status",
            return_value={
                "projectName": "rovik-keevs",
                "serviceName": "bot",
                "latestDeployment": {"status": "SUCCESS"},
            },
        ),
        patch(
            "cosinabox.cli.auth_refresh._railway.get_variable",
            side_effect=lambda name: {
                "GOOGLE_OAUTH_CLIENT_ID": "cid-from-railway",
                "GOOGLE_OAUTH_CLIENT_SECRET": "sec-from-railway",
            }.get(name),
        ),
        patch(
            "cosinabox.cli.auth_refresh._railway.set_variable",
            side_effect=lambda n, v: set_calls.append((n, v)),
        ),
        patch("cosinabox.cli.auth_refresh._railway.redeploy") as redeploy,
        patch(
            "cosinabox.cli.auth_refresh._railway.wait_for_deployment",
            return_value=True,
        ),
        patch(
            "cosinabox.cli.auth_refresh.mint_refresh_token",
            return_value="rt-fresh-from-google",
        ),
    ):
        result = CliRunner().invoke(cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes"])

    assert result.exit_code == 0, result.output
    # Single-account path: no picker shown.
    assert "Pick" not in result.output and "Choose" not in result.output
    # The chosen account is announced.
    assert "rovik@example.com" in result.output
    # The token was written to slot _1.
    assert ("GOOGLE_OAUTH_REFRESH_TOKEN_1", "rt-fresh-from-google") in set_calls
    # Redeploy fired and we reported success.
    redeploy.assert_called_once()
    assert "redeploy" in result.output.lower()
    assert "success" in result.output.lower() or "auth_health" in result.output.lower()


# Helper consumed by M5/M6 — wires the bundle of patches needed for the
# happy-path orchestration so individual tests can vary one piece without
# repeating the full mock stack.
def _patch_happy_path_railway(token_for_email: dict[str, str]) -> Any:
    from contextlib import ExitStack

    set_calls: list[tuple[str, str]] = []

    def enter() -> tuple[ExitStack, list[tuple[str, str]]]:
        stack = ExitStack()
        stack.enter_context(
            patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=True)
        )
        stack.enter_context(patch("cosinabox.cli.auth_refresh._railway.whoami", return_value="x"))
        stack.enter_context(
            patch(
                "cosinabox.cli.auth_refresh._railway.status",
                return_value={
                    "projectName": "rovik-keevs",
                    "serviceName": "bot",
                    "latestDeployment": {"status": "SUCCESS"},
                },
            )
        )
        stack.enter_context(
            patch(
                "cosinabox.cli.auth_refresh._railway.get_variable",
                side_effect=lambda n: {
                    "GOOGLE_OAUTH_CLIENT_ID": "cid",
                    "GOOGLE_OAUTH_CLIENT_SECRET": "sec",
                }.get(n),
            )
        )
        stack.enter_context(
            patch(
                "cosinabox.cli.auth_refresh._railway.set_variable",
                side_effect=lambda n, v: set_calls.append((n, v)),
            )
        )
        stack.enter_context(patch("cosinabox.cli.auth_refresh._railway.redeploy"))
        stack.enter_context(
            patch(
                "cosinabox.cli.auth_refresh._railway.wait_for_deployment",
                return_value=True,
            )
        )

        def fake_mint(*, client_id: str, client_secret: str, expected_email: str | None) -> str:
            assert expected_email is not None
            return token_for_email[expected_email]

        stack.enter_context(
            patch("cosinabox.cli.auth_refresh.mint_refresh_token", side_effect=fake_mint)
        )
        return stack, set_calls

    return enter


def test_auth_refresh_account_flag_selects_named_account(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(
        tmp_path,
        [{"email": "primary@example.com"}, {"email": "secondary@example.com"}],
    )
    enter = _patch_happy_path_railway({"secondary@example.com": "rt-secondary"})
    stack, set_calls = enter()
    with stack:
        result = CliRunner().invoke(
            cli,
            [
                "-C",
                str(cfg_dir),
                "auth",
                "refresh",
                "--account",
                "secondary@example.com",
                "--yes",
            ],
        )
    assert result.exit_code == 0, result.output
    # Slot 2 because secondary is accounts[1].
    assert ("GOOGLE_OAUTH_REFRESH_TOKEN_2", "rt-secondary") in set_calls


def test_auth_refresh_account_flag_unknown_email_errors(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(tmp_path, [{"email": "primary@example.com"}])
    # No mocks needed past load_integrations — we should bail before
    # touching Railway.
    result = CliRunner().invoke(
        cli,
        [
            "-C",
            str(cfg_dir),
            "auth",
            "refresh",
            "--account",
            "stranger@example.com",
            "--yes",
        ],
    )
    assert result.exit_code != 0
    assert "stranger@example.com" in result.output
    assert "primary@example.com" in result.output  # configured ones listed


def test_auth_refresh_picker_writes_to_chosen_slot(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(
        tmp_path,
        [{"email": "primary@example.com"}, {"email": "secondary@example.com"}],
    )
    enter = _patch_happy_path_railway({"secondary@example.com": "rt-picked"})
    stack, set_calls = enter()
    with stack:
        # CliRunner's `input` feeds stdin to click.prompt.
        result = CliRunner().invoke(
            cli,
            ["-C", str(cfg_dir), "auth", "refresh", "--yes"],
            input="2\n",
        )
    assert result.exit_code == 0, result.output
    # Picker lines printed.
    assert "1. primary@example.com" in result.output
    assert "2. secondary@example.com" in result.output
    assert ("GOOGLE_OAUTH_REFRESH_TOKEN_2", "rt-picked") in set_calls


def test_auth_refresh_account_flag_is_case_insensitive(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(tmp_path, [{"email": "Mixed@Example.COM"}])
    enter = _patch_happy_path_railway({"Mixed@Example.COM": "rt-case"})
    stack, set_calls = enter()
    with stack:
        result = CliRunner().invoke(
            cli,
            [
                "-C",
                str(cfg_dir),
                "auth",
                "refresh",
                "--account",
                "mixed@example.com",
                "--yes",
            ],
        )
    assert result.exit_code == 0, result.output
    assert ("GOOGLE_OAUTH_REFRESH_TOKEN_1", "rt-case") in set_calls
