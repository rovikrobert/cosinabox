"""Unit tests for the thin Railway CLI adapter (cli/_railway.py).

All `subprocess` invocations are mocked. These tests do not touch the
network or the user's Railway state.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from cosinabox.cli import _railway


def _make_completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_cli_available_true_when_on_path() -> None:
    with patch("cosinabox.cli._railway.shutil.which", return_value="/usr/local/bin/railway"):
        assert _railway.cli_available() is True


def test_cli_available_false_when_missing() -> None:
    with patch("cosinabox.cli._railway.shutil.which", return_value=None):
        assert _railway.cli_available() is False


def test_whoami_returns_user_string() -> None:
    with patch(
        "cosinabox.cli._railway.subprocess.run",
        return_value=_make_completed(stdout="rovik@example.com\n"),
    ):
        assert _railway.whoami() == "rovik@example.com"


def test_whoami_raises_railway_error_on_nonzero() -> None:
    with (
        patch(
            "cosinabox.cli._railway.subprocess.run",
            return_value=_make_completed(returncode=1, stdout="not logged in"),
        ),
        pytest.raises(_railway.RailwayError) as exc,
    ):
        _railway.whoami()
    assert "railway login" in str(exc.value).lower()


# `railway status --json` schema observed against railway 4.30.2 (2026-05-06):
# Top level: {id, name, deletedAt, workspace, environments, services}.
# - "name" is the project name.
# - "services.edges[].node.name" is each service name.
# There is NO "projectName" / "serviceName" / "latestDeployment" key. Tests
# below pin the real schema so a future refactor can't silently revert to
# the imaginary one.

_REAL_STATUS_PAYLOAD = {
    "id": "p-uuid",
    "name": "rovik-keevs",
    "deletedAt": None,
    "workspace": {"id": "w-uuid", "name": "Personal"},
    "environments": {"edges": [{"node": {"id": "e-uuid", "name": "production"}}]},
    "services": {"edges": [{"node": {"id": "s-uuid", "name": "bot"}}]},
}


def test_status_returns_real_railway_4_schema() -> None:
    with patch(
        "cosinabox.cli._railway.subprocess.run",
        return_value=_make_completed(stdout=json.dumps(_REAL_STATUS_PAYLOAD)),
    ):
        s = _railway.status()
    assert s["name"] == "rovik-keevs"
    # Service name lives nested.
    svc = s["services"]["edges"][0]["node"]
    assert svc["name"] == "bot"


def test_status_raises_when_no_service_linked() -> None:
    # `railway status --json` exits non-zero when no service is linked.
    with (
        patch(
            "cosinabox.cli._railway.subprocess.run",
            return_value=_make_completed(returncode=1, stdout=""),
        ),
        pytest.raises(_railway.RailwayError) as exc,
    ):
        _railway.status()
    assert "railway link" in str(exc.value).lower()


def test_get_variable_returns_value() -> None:
    payload = {"GOOGLE_OAUTH_CLIENT_ID": "cid-123", "OTHER": "x"}
    with patch(
        "cosinabox.cli._railway.subprocess.run",
        return_value=_make_completed(stdout=json.dumps(payload)),
    ):
        assert _railway.get_variable("GOOGLE_OAUTH_CLIENT_ID") == "cid-123"


def test_get_variable_returns_none_when_absent() -> None:
    payload = {"OTHER": "x"}
    with patch(
        "cosinabox.cli._railway.subprocess.run",
        return_value=_make_completed(stdout=json.dumps(payload)),
    ):
        assert _railway.get_variable("MISSING") is None


def test_set_variable_uses_stdin_not_argv() -> None:
    """Refresh tokens are secrets; argv is observable via `ps -ef` for any
    user on the box. Using --stdin keeps the value out of argv entirely.
    """
    captured: dict[str, object] = {}

    def fake_run(args: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = list(args)
        captured["input"] = kw.get("input")
        return _make_completed()

    with patch("cosinabox.cli._railway.subprocess.run", side_effect=fake_run):
        _railway.set_variable("GOOGLE_OAUTH_REFRESH_TOKEN_1", "rt-secret-1234")

    args = captured["args"]
    assert isinstance(args, list)
    # New subcommand syntax: `railway variable set <KEY> --stdin`. The
    # value MUST NOT appear anywhere in argv.
    assert "variable" in args  # singular subcommand
    assert "set" in args
    assert "--stdin" in args
    assert "GOOGLE_OAUTH_REFRESH_TOKEN_1" in args
    joined = " ".join(args)
    assert "rt-secret-1234" not in joined  # no value leakage in argv
    # The value reaches the CLI via subprocess stdin instead.
    assert captured["input"] == "rt-secret-1234"


def test_set_variable_error_does_not_leak_value() -> None:
    """Railway's CLI can echo the K=V (or just the value) on failure
    (e.g. validation error). The adapter must NOT fold raw stdout/stderr
    into the user-facing error or the token leaks into a click exception.
    """
    leaky_stdout = "error: variable rt-secret-1234 rejected by Railway"
    with (
        patch(
            "cosinabox.cli._railway.subprocess.run",
            return_value=_make_completed(returncode=1, stdout=leaky_stdout),
        ),
        pytest.raises(_railway.RailwayError) as exc,
    ):
        _railway.set_variable("GOOGLE_OAUTH_REFRESH_TOKEN_1", "rt-secret-1234")
    # The variable name SHOULD be in the error so the user knows what
    # failed; the value must NOT be.
    assert "GOOGLE_OAUTH_REFRESH_TOKEN_1" in str(exc.value)
    assert "rt-secret-1234" not in str(exc.value)


def test_redeploy_invokes_deploy_verb() -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = list(args)
        return _make_completed(stdout="building...")

    with patch("cosinabox.cli._railway.subprocess.run", side_effect=fake_run):
        _railway.redeploy()

    assert "redeploy" in captured["args"]
    # -y / --yes is required to skip the interactive confirmation.
    assert any(flag in captured["args"] for flag in ("-y", "--yes"))


# `wait_for_deployment` was removed (S1+S2 stress-test fix): railway 4.x
# doesn't expose deployment status via `railway status --json`, so the
# poll loop always timed out and reported successful redeploys as
# failures. The orchestrator now relies on `auth_health` for verification.
# Surface the removal so a future plan doesn't accidentally re-introduce it.
def test_wait_for_deployment_function_does_not_exist() -> None:
    assert not hasattr(_railway, "wait_for_deployment")
