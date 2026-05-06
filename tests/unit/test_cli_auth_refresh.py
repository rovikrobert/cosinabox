"""Tests for `cosinabox auth refresh`.

All Railway CLI calls and the OAuth consent flow are mocked. These
tests verify orchestration logic, not the real Railway CLI or Google
OAuth (those are tested independently in their own modules).

Status payloads in this file follow the real ``railway status --json``
schema verified against railway 4.30.2 on 2026-05-06: top-level
``name`` for the project, ``services.edges[].node.name`` for services.
There is no ``latestDeployment`` / ``projectName`` / ``serviceName``
key anywhere in real output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml
from click.testing import CliRunner

from cosinabox.cli.main import cli

# Real ``railway status --json`` shape from railway 4.30.2.
_REAL_STATUS = {
    "id": "p-uuid",
    "name": "rovik-keevs",
    "deletedAt": None,
    "workspace": {"id": "w-uuid", "name": "Personal"},
    "environments": {"edges": [{"node": {"id": "e-uuid", "name": "production"}}]},
    "services": {"edges": [{"node": {"id": "s-uuid", "name": "bot"}}]},
}


def _write_integrations(tmp_path: Path, accounts: list[dict[str, str]]) -> Path:
    cfg = {
        "schema_version": 1,
        "integrations": {"google": {"enabled": True, "accounts": accounts}},
    }
    (tmp_path / "integrations.yaml").write_text(yaml.safe_dump(cfg))
    return tmp_path


def test_auth_refresh_happy_path_single_account(tmp_path: Path) -> None:
    """Single-account user → no picker → mint → set _1 → redeploy → exit OK."""
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])

    set_calls: list[tuple[str, str]] = []

    with (
        patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=True),
        patch(
            "cosinabox.cli.auth_refresh._railway.whoami",
            return_value="rovik@example.com",
        ),
        patch("cosinabox.cli.auth_refresh._railway.status", return_value=_REAL_STATUS),
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
    # The detected project + service render correctly from the real schema.
    assert "rovik-keevs" in result.output
    assert "bot" in result.output
    # The token was written to slot _1.
    assert ("GOOGLE_OAUTH_REFRESH_TOKEN_1", "rt-fresh-from-google") in set_calls
    # Redeploy fired and we pointed the user at auth_health for verification.
    redeploy.assert_called_once()
    assert "redeploy" in result.output.lower()
    assert "auth_health" in result.output.lower()


# Helper that wires the bundle of patches needed for the happy-path
# orchestration so individual tests can vary one piece without
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
            patch("cosinabox.cli.auth_refresh._railway.status", return_value=_REAL_STATUS)
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
    assert "primary@example.com" in result.output


def test_auth_refresh_picker_writes_to_chosen_slot(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(
        tmp_path,
        [{"email": "primary@example.com"}, {"email": "secondary@example.com"}],
    )
    enter = _patch_happy_path_railway({"secondary@example.com": "rt-picked"})
    stack, set_calls = enter()
    with stack:
        result = CliRunner().invoke(
            cli,
            ["-C", str(cfg_dir), "auth", "refresh", "--yes"],
            input="2\n",
        )
    assert result.exit_code == 0, result.output
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


# --- Failure modes ---


def test_railway_cli_missing_friendly_error(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])
    with patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=False):
        result = CliRunner().invoke(cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes"])
    assert result.exit_code != 0
    assert "railway cli" in result.output.lower()
    assert "install" in result.output.lower()


def test_railway_not_logged_in_friendly_error(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])
    from cosinabox.cli._railway import RailwayError

    with (
        patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=True),
        patch(
            "cosinabox.cli.auth_refresh._railway.whoami",
            side_effect=RailwayError("Not logged in to Railway. Run: railway login"),
        ),
    ):
        result = CliRunner().invoke(cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes"])
    assert result.exit_code != 0
    assert "railway login" in result.output.lower()


def test_railway_no_service_linked_friendly_error(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])
    from cosinabox.cli._railway import RailwayError

    with (
        patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=True),
        patch("cosinabox.cli.auth_refresh._railway.whoami", return_value="x"),
        patch(
            "cosinabox.cli.auth_refresh._railway.status",
            side_effect=RailwayError(
                "No Railway service linked in this directory. Run: railway link"
            ),
        ),
    ):
        result = CliRunner().invoke(cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes"])
    assert result.exit_code != 0
    assert "railway link" in result.output.lower()


def test_account_mismatch_surfaces_friendly_error(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(tmp_path, [{"email": "intended@example.com"}])
    from cosinabox.cli.auth_google import AccountMismatchError

    with (
        patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=True),
        patch("cosinabox.cli.auth_refresh._railway.whoami", return_value="x"),
        patch("cosinabox.cli.auth_refresh._railway.status", return_value=_REAL_STATUS),
        patch(
            "cosinabox.cli.auth_refresh._railway.get_variable",
            side_effect=lambda n: {
                "GOOGLE_OAUTH_CLIENT_ID": "cid",
                "GOOGLE_OAUTH_CLIENT_SECRET": "sec",
            }.get(n),
        ),
        patch(
            "cosinabox.cli.auth_refresh.mint_refresh_token",
            side_effect=AccountMismatchError(
                "Consent screen completed with stranger@example.com, not "
                "intended@example.com. Refusing to print the token."
            ),
        ),
        patch("cosinabox.cli.auth_refresh._railway.set_variable") as set_var,
        patch("cosinabox.cli.auth_refresh._railway.redeploy") as redeploy,
    ):
        result = CliRunner().invoke(cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes"])
    assert result.exit_code != 0
    assert "stranger@example.com" in result.output
    assert "intended@example.com" in result.output
    set_var.assert_not_called()
    redeploy.assert_not_called()


def test_announces_chosen_slot_in_output(tmp_path: Path) -> None:
    """Spec failure #5: the _N → email mapping must be visible to the user."""
    cfg_dir = _write_integrations(
        tmp_path,
        [{"email": "first@example.com"}, {"email": "second@example.com"}],
    )
    enter = _patch_happy_path_railway({"second@example.com": "rt-x"})
    stack, _set_calls = enter()
    with stack:
        result = CliRunner().invoke(
            cli,
            [
                "-C",
                str(cfg_dir),
                "auth",
                "refresh",
                "--account",
                "second@example.com",
                "--yes",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "GOOGLE_OAUTH_REFRESH_TOKEN_2" in result.output


def test_legacy_unsuffixed_token_emits_warning(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])

    def fake_get(name: str) -> str | None:
        return {
            "GOOGLE_OAUTH_CLIENT_ID": "cid",
            "GOOGLE_OAUTH_CLIENT_SECRET": "sec",
            "GOOGLE_OAUTH_REFRESH_TOKEN": "old-token",
        }.get(name)

    with (
        patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=True),
        patch("cosinabox.cli.auth_refresh._railway.whoami", return_value="x"),
        patch("cosinabox.cli.auth_refresh._railway.status", return_value=_REAL_STATUS),
        patch(
            "cosinabox.cli.auth_refresh._railway.get_variable",
            side_effect=fake_get,
        ),
        patch("cosinabox.cli.auth_refresh._railway.set_variable"),
        patch("cosinabox.cli.auth_refresh._railway.redeploy"),
        patch(
            "cosinabox.cli.auth_refresh.mint_refresh_token",
            return_value="rt-new",
        ),
    ):
        result = CliRunner().invoke(cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes"])
    assert result.exit_code == 0, result.output
    assert "legacy" in result.output.lower()
    assert "GOOGLE_OAUTH_REFRESH_TOKEN_1" in result.output


def test_no_google_integration_errors(tmp_path: Path) -> None:
    cfg = {"schema_version": 1, "integrations": {"google": {"enabled": False}}}
    (tmp_path / "integrations.yaml").write_text(yaml.safe_dump(cfg))
    result = CliRunner().invoke(cli, ["-C", str(tmp_path), "auth", "refresh", "--yes"])
    assert result.exit_code != 0
    assert "not enabled" in result.output.lower() or "nothing to refresh" in result.output.lower()


def test_missing_oauth_client_creds_friendly_error(tmp_path: Path) -> None:
    """Spec failure #2 (Railway truncated CLIENT_ID): if creds are missing
    on the deploy, surface a clear instruction instead of a generic
    OAuth library error."""
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])

    with (
        patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=True),
        patch("cosinabox.cli.auth_refresh._railway.whoami", return_value="x"),
        patch("cosinabox.cli.auth_refresh._railway.status", return_value=_REAL_STATUS),
        patch(
            "cosinabox.cli.auth_refresh._railway.get_variable",
            return_value=None,
        ),
        patch("cosinabox.cli.auth_refresh.mint_refresh_token") as mint,
    ):
        result = CliRunner().invoke(cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes"])
    assert result.exit_code != 0
    assert "GOOGLE_OAUTH_CLIENT_ID" in result.output
    mint.assert_not_called()


# --- Stress-test fixes (S5, S6) ---


def test_orchestrator_catches_runtime_error_from_mint(tmp_path: Path) -> None:
    """S5: if google_auth_oauthlib isn't installed, mint_refresh_token
    raises RuntimeError. Orchestrator must surface that as a friendly
    ClickException, not a raw traceback to the user.
    """
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])

    with (
        patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=True),
        patch("cosinabox.cli.auth_refresh._railway.whoami", return_value="x"),
        patch("cosinabox.cli.auth_refresh._railway.status", return_value=_REAL_STATUS),
        patch(
            "cosinabox.cli.auth_refresh._railway.get_variable",
            side_effect=lambda n: {
                "GOOGLE_OAUTH_CLIENT_ID": "cid",
                "GOOGLE_OAUTH_CLIENT_SECRET": "sec",
            }.get(n),
        ),
        patch(
            "cosinabox.cli.auth_refresh.mint_refresh_token",
            side_effect=RuntimeError(
                "google-auth-oauthlib is not installed. Run: pip install google-auth-oauthlib"
            ),
        ),
    ):
        result = CliRunner().invoke(cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes"])
    assert result.exit_code != 0
    # Friendly ClickException, not a Python traceback.
    assert "Traceback" not in result.output
    assert "google-auth-oauthlib" in result.output
    assert "pip install" in result.output


def test_orchestrator_handles_malformed_yaml(tmp_path: Path) -> None:
    """S6: a syntax typo in integrations.yaml must surface a friendly
    error pointing at the file + the validate command, not a raw YAML
    traceback.
    """
    (tmp_path / "integrations.yaml").write_text(
        "schema_version: 1\nintegrations:\n  google:\n    enabled: true\n"
        "    accounts:\n      - email: rovik@example.com\n      bad-indent: x\n"
    )
    result = CliRunner().invoke(cli, ["-C", str(tmp_path), "auth", "refresh", "--yes"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "integrations.yaml" in result.output
    assert "cosinabox validate" in result.output


# --- Stress-test fixes (S1, S2): real railway status schema ---


def test_status_displays_real_railway_4_schema_fields(tmp_path: Path) -> None:
    """S1+S2: the project+service line must read from real railway 4.x
    fields ('name' for project, 'services.edges[].node.name' for
    services), not from imaginary 'projectName' / 'serviceName' keys.
    """
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])
    enter = _patch_happy_path_railway({"rovik@example.com": "rt-x"})
    stack, _ = enter()
    with stack:
        result = CliRunner().invoke(cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes"])
    assert result.exit_code == 0, result.output
    # Real schema → real fields render. "(unknown)" sentinels would
    # mean we silently regressed back to reading projectName/serviceName.
    assert "rovik-keevs" in result.output  # from _REAL_STATUS["name"]
    assert "bot" in result.output  # from _REAL_STATUS["services"]["edges"][0]["node"]["name"]
    assert "(unknown" not in result.output


def test_no_wait_flag_no_longer_exists(tmp_path: Path) -> None:
    """S1+S2: --no-wait was a flag on the old wait_for_deployment path.
    With wait_for_deployment removed, the flag is removed too. Surface
    the removal so CI fails loudly if someone re-introduces it without
    re-introducing the broken polling.
    """
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])
    result = CliRunner().invoke(cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes", "--no-wait"])
    # Click rejects unknown flags with exit code 2.
    assert result.exit_code != 0
    assert "no-wait" in result.output.lower() or "no such option" in result.output.lower()
