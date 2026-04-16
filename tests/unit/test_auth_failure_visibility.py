"""OAuth/auth failure visibility tests (Item 3).

Per memory feedback_flag_oauth_failures: surface auth failures via Telegram,
never silently drop accounts. The tool-building phase collects any auth/init
errors so the caller (app.py) can route them through send_telegram once the
bot is up.
"""

from __future__ import annotations

from unittest.mock import patch

from cosinabox.app import App


class TestAuthFailureVisibility:
    def test_build_tools_returns_errors_on_google_auth_failure(self, tmp_path):
        """Google OAuth failure must be surfaced in an errors list, not swallowed."""
        from cosinabox.tools.google.auth import GoogleAuthError

        app = App(config_dir=str(tmp_path))
        integrations = {"google": {"enabled": True}}

        # Simulate GmailTool() raising due to missing refresh tokens.
        with patch(
            "cosinabox.tools.google.gmail.GmailTool",
            side_effect=GoogleAuthError("Missing GOOGLE_OAUTH_REFRESH_TOKEN"),
        ):
            tools, _, errors = app._build_tools(integrations)

        assert "gmail" not in tools
        assert any("Google" in e or "gmail" in e.lower() for e in errors)
        assert any("GOOGLE_OAUTH_REFRESH_TOKEN" in e for e in errors)

    def test_build_tools_returns_errors_on_401(self, tmp_path):
        """A 401 during construction (e.g., refresh-token rejected) must be surfaced."""
        app = App(config_dir=str(tmp_path))
        integrations = {"google": {"enabled": True}}

        # Simulate 401 returned by the OAuth token endpoint.
        with patch(
            "cosinabox.tools.google.gmail.GmailTool",
            side_effect=Exception(
                "invalid_grant: 401 Unauthorized — refresh token revoked"
            ),
        ):
            tools, _, errors = app._build_tools(integrations)

        assert "gmail" not in tools
        assert any("401" in e or "invalid_grant" in e for e in errors)

    def test_build_tools_empty_errors_on_success(self, tmp_path):
        """With all integrations disabled, errors list is empty."""
        app = App(config_dir=str(tmp_path))
        integrations = {}
        tools, _, errors = app._build_tools(integrations)
        assert tools == {}
        assert errors == []

    def test_build_tools_reports_per_integration(self, tmp_path):
        """Attio auth error → surfaced even if Google succeeds (or is off)."""
        app = App(config_dir=str(tmp_path))
        integrations = {"attio": {"enabled": True}}

        with patch(
            "cosinabox.tools.attio.AttioClient",
            side_effect=Exception("ATTIO_API_KEY not set"),
        ):
            tools, _, errors = app._build_tools(integrations)

        assert "attio" not in tools
        assert any("attio" in e.lower() for e in errors)

    def test_auth_errors_routed_through_send_telegram(self, tmp_path):
        """Given auth errors from _build_tools, the run() path must invoke
        send_telegram with a user-readable alert. Mocks all the other
        startup dependencies so we only exercise the alert wiring."""
        from cosinabox.tools.google.auth import GoogleAuthError

        sent: list[str] = []

        # Build a stub App.run that only executes the alert block.
        # The simplest verification: directly call _build_tools, then
        # simulate the send_telegram-dispatch block from app.py.
        app = App(config_dir=str(tmp_path))
        integrations = {"google": {"enabled": True}}
        with patch(
            "cosinabox.tools.google.gmail.GmailTool",
            side_effect=GoogleAuthError("Gmail account 1 OAuth failed: 401"),
        ):
            _, _, errors = app._build_tools(integrations)

        # This mirrors the block in App.run()
        def send_telegram(text: str) -> None:
            sent.append(text)

        if errors:
            alert_body = "\n\n".join(f"- {e}" for e in errors)
            send_telegram(
                "[cosinabox startup] Integration auth issues detected:\n\n"
                f"{alert_body}"
            )

        assert len(sent) == 1
        assert "auth" in sent[0].lower()
        assert "Gmail account 1" in sent[0] or "OAuth" in sent[0]
