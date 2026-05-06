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


def test_status_returns_parsed_dict() -> None:
    payload = {"projectId": "p1", "projectName": "rovik-keevs", "serviceName": "bot"}
    with patch(
        "cosinabox.cli._railway.subprocess.run",
        return_value=_make_completed(stdout=json.dumps(payload)),
    ):
        s = _railway.status()
    assert s["projectName"] == "rovik-keevs"
    assert s["serviceName"] == "bot"


def test_status_raises_when_no_service_linked() -> None:
    # `railway status --json` exits non-zero in some "no service" states; in
    # others it returns a payload missing the service field. Cover the
    # nonzero-exit case here; the orchestrator checks for missing fields
    # at the call site.
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


def test_set_variable_passes_kv_to_cli() -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = list(args)
        return _make_completed()

    with patch("cosinabox.cli._railway.subprocess.run", side_effect=fake_run):
        _railway.set_variable("GOOGLE_OAUTH_REFRESH_TOKEN_1", "rt-new")

    assert "variables" in captured["args"]
    # The CLI form is `railway variables --set "K=V"`. The K=V pair must
    # appear intact in the command for Railway to accept it.
    joined = " ".join(captured["args"])
    assert "GOOGLE_OAUTH_REFRESH_TOKEN_1=rt-new" in joined


def test_set_variable_raises_on_failure() -> None:
    with (
        patch(
            "cosinabox.cli._railway.subprocess.run",
            return_value=_make_completed(returncode=1, stdout="permission denied"),
        ),
        pytest.raises(_railway.RailwayError),
    ):
        _railway.set_variable("X", "y")


def test_redeploy_invokes_deploy_verb() -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = list(args)
        return _make_completed(stdout="building...")

    with patch("cosinabox.cli._railway.subprocess.run", side_effect=fake_run):
        _railway.redeploy()

    # Either `railway redeploy` or `railway up --ci` is acceptable; the
    # impl picks one. Test that *some* deploy verb is invoked.
    assert any(verb in captured["args"] for verb in ("redeploy", "up"))


def test_wait_for_deployment_polls_until_success() -> None:
    """Polls `railway status --json` until deployment reaches SUCCESS."""
    payloads = iter(
        [
            json.dumps({"latestDeployment": {"status": "BUILDING"}}),
            json.dumps({"latestDeployment": {"status": "DEPLOYING"}}),
            json.dumps({"latestDeployment": {"status": "SUCCESS"}}),
        ]
    )
    with (
        patch(
            "cosinabox.cli._railway.subprocess.run",
            side_effect=lambda *_a, **_kw: _make_completed(stdout=next(payloads)),
        ),
        patch("cosinabox.cli._railway.time.sleep") as fake_sleep,
    ):
        ok = _railway.wait_for_deployment(timeout_seconds=60, poll_interval=2)
    assert ok is True
    assert fake_sleep.called


def test_wait_for_deployment_returns_false_on_failure_status() -> None:
    payloads = iter(
        [
            json.dumps({"latestDeployment": {"status": "BUILDING"}}),
            json.dumps({"latestDeployment": {"status": "FAILED"}}),
        ]
    )
    with (
        patch(
            "cosinabox.cli._railway.subprocess.run",
            side_effect=lambda *_a, **_kw: _make_completed(stdout=next(payloads)),
        ),
        patch("cosinabox.cli._railway.time.sleep"),
    ):
        ok = _railway.wait_for_deployment(timeout_seconds=60, poll_interval=2)
    assert ok is False


def test_wait_for_deployment_returns_false_on_timeout() -> None:
    with (
        patch(
            "cosinabox.cli._railway.subprocess.run",
            return_value=_make_completed(
                stdout=json.dumps({"latestDeployment": {"status": "BUILDING"}})
            ),
        ),
        patch("cosinabox.cli._railway.time.sleep"),
        # First monotonic call is the loop's `start` sentinel; subsequent
        # calls are the loop guard. Returning increasing values guarantees
        # the elapsed > timeout check fires after one iteration.
        patch("cosinabox.cli._railway.time.monotonic", side_effect=[0, 0, 100, 200]),
    ):
        ok = _railway.wait_for_deployment(timeout_seconds=60, poll_interval=2)
    assert ok is False
