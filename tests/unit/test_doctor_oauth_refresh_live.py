"""Tests for OAuthRefreshLiveCheck — actively exercises refresh tokens.

All `cred.refresh()` calls are mocked; these tests do not touch the
network. The real-Google smoke test (M5b in the plan) is the
maintainer-run gate before merge.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from cosinabox.doctor.checks import OAuthRefreshLiveCheck


def _write_integrations(tmp_path: Path, accounts: list[dict[str, str]]) -> Path:
    cfg = {
        "schema_version": 1,
        "integrations": {"google": {"enabled": True, "accounts": accounts}},
    }
    (tmp_path / "integrations.yaml").write_text(yaml.safe_dump(cfg))
    return tmp_path


def test_check_is_marked_network() -> None:
    """OAuthRefreshLiveCheck must declare network=True so --offline skips it."""
    assert OAuthRefreshLiveCheck.network is True


def test_pass_when_all_creds_refresh_successfully(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])
    fake_cred = MagicMock()
    fake_cred.refresh = MagicMock(return_value=None)

    with patch(
        "cosinabox.doctor.checks.build_all_credentials",
        return_value=[fake_cred],
    ):
        result = OAuthRefreshLiveCheck().run(config_dir=cfg_dir, history={})

    assert result.status == "pass"
    # Pass message should reference how many accounts were probed.
    assert "1" in result.message


def test_fail_when_one_cred_refresh_raises(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(
        tmp_path,
        [{"email": "ok@example.com"}, {"email": "dead@example.com"}],
    )
    from google.auth.exceptions import RefreshError

    ok = MagicMock()
    ok.refresh = MagicMock(return_value=None)
    bad = MagicMock()
    bad.refresh = MagicMock(side_effect=RefreshError("token has been expired or revoked"))

    with patch(
        "cosinabox.doctor.checks.build_all_credentials",
        return_value=[ok, bad],
    ):
        result = OAuthRefreshLiveCheck().run(config_dir=cfg_dir, history={})

    assert result.status == "fail"
    # Failure message identifies the bad account by email and points at the fix.
    assert "dead@example.com" in result.message
    assert "cosinabox auth refresh" in result.message
    # The healthy account is NOT named in the failure — keep the fix focused.
    assert "ok@example.com" not in result.message


def test_warn_when_credentials_factory_raises_googleautherror(tmp_path: Path) -> None:
    """Missing CLIENT_ID/SECRET → build_all_credentials raises GoogleAuthError.
    Doctor warns rather than failing — the user opted out of Google by not
    setting the env vars.
    """
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])

    from cosinabox.tools.google.auth import GoogleAuthError

    with patch(
        "cosinabox.doctor.checks.build_all_credentials",
        side_effect=GoogleAuthError(
            "Missing GOOGLE_OAUTH_CLIENT_ID or GOOGLE_OAUTH_CLIENT_SECRET. "
            "Run `cosinabox auth google` to configure."
        ),
    ):
        result = OAuthRefreshLiveCheck().run(config_dir=cfg_dir, history={})

    assert result.status == "warn"
    assert "google" in result.message.lower()


def test_warn_when_google_integration_not_enabled(tmp_path: Path) -> None:
    """If integrations.yaml has google.enabled=false, the check has nothing
    to probe. Warn rather than fail — the user opted out."""
    cfg = {"schema_version": 1, "integrations": {"google": {"enabled": False}}}
    (tmp_path / "integrations.yaml").write_text(yaml.safe_dump(cfg))

    result = OAuthRefreshLiveCheck().run(config_dir=tmp_path, history={})
    assert result.status == "warn"
    assert (
        "not enabled" in result.message.lower()
        or "disabled" in result.message.lower()
        or "nothing to probe" in result.message.lower()
    )


def test_failure_message_uses_account_index_when_email_missing(tmp_path: Path) -> None:
    """Edge: integrations.yaml missing the accounts list, but
    build_all_credentials returns creds (e.g. legacy single-account env vars).
    Fall back to '#1', '#2' labels so the message is still actionable.
    """
    (tmp_path / "integrations.yaml").write_text(
        "schema_version: 1\nintegrations:\n  google:\n    enabled: true\n"
    )
    from google.auth.exceptions import RefreshError

    bad = MagicMock()
    bad.refresh = MagicMock(side_effect=RefreshError("revoked"))

    with patch(
        "cosinabox.doctor.checks.build_all_credentials",
        return_value=[bad],
    ):
        result = OAuthRefreshLiveCheck().run(config_dir=tmp_path, history={})

    assert result.status == "fail"
    assert "#1" in result.message or "account 1" in result.message.lower()
    assert "cosinabox auth refresh" in result.message


def test_transient_error_returns_warn_not_fail(tmp_path: Path) -> None:
    """A network blip (TransportError, etc.) is not a "token is dead"
    signal — surface as warn so the user knows something happened but
    doesn't panic-rotate a healthy token.
    """
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])
    from google.auth.exceptions import TransportError

    bad = MagicMock()
    bad.refresh = MagicMock(side_effect=TransportError("connection reset"))

    with patch(
        "cosinabox.doctor.checks.build_all_credentials",
        return_value=[bad],
    ):
        result = OAuthRefreshLiveCheck().run(config_dir=cfg_dir, history={})

    assert result.status == "warn"
    assert "transient" in result.message.lower() or "network" in result.message.lower()
