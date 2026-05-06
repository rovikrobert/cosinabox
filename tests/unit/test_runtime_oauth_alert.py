"""Runtime OAuth failure must be surfaced via Telegram alert.

Bug: PR #22 item 3 added alerting at startup, but Google tokens can
expire at runtime during scheduled jobs. These failures are silent.

Fix: catch RefreshError in Google tool wrappers, send a Telegram alert
once, and return a graceful error string.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from google.auth.exceptions import RefreshError

from cosinabox.tools.google import _runtime_alert
from cosinabox.tools.google.calendar import CalendarTool
from cosinabox.tools.google.gmail import GmailTool


def _reset_alert_state() -> None:
    """Reset the deduplication state between tests."""
    _runtime_alert._last_alert_at = 0.0


class TestCalendarRuntimeOAuthAlert:
    def test_refresh_error_sends_telegram_alert(self) -> None:
        """list_events raising RefreshError -> send_telegram called with auth alert."""
        _reset_alert_state()
        service = MagicMock()
        service.events().list().execute.side_effect = RefreshError("token expired")
        cal = CalendarTool(service=service)

        start = datetime(2026, 4, 15, tzinfo=UTC)
        end = datetime(2026, 4, 16, tzinfo=UTC)

        with patch("cosinabox.tools.google.calendar._runtime_oauth_alert") as mock_alert:
            result = cal.list_events(start=start, end=end)

        mock_alert.assert_called_once()
        # Should return empty list, not crash
        assert result == []

    def test_refresh_error_alert_deduplicates(self) -> None:
        """Only one alert per token failure, not every call.

        This test exercises the real deduplication logic in _runtime_alert,
        NOT the patched version.
        """
        _reset_alert_state()
        service = MagicMock()
        service.events().list().execute.side_effect = RefreshError("token expired")
        cal = CalendarTool(service=service)

        start = datetime(2026, 4, 15, tzinfo=UTC)
        end = datetime(2026, 4, 16, tzinfo=UTC)

        sent: list[str] = []
        _runtime_alert._send_telegram_fn = lambda msg: sent.append(msg)
        try:
            cal.list_events(start=start, end=end)
            cal.list_events(start=start, end=end)
            cal.list_events(start=start, end=end)
        finally:
            _runtime_alert._send_telegram_fn = None

        # Should only alert once thanks to deduplication
        assert len(sent) == 1
        assert "OAuth" in sent[0]


class TestRuntimeAlertAccountLabel:
    """Alert messages must identify which account failed in multi-account setups.

    Without this, "Google OAuth token expired" gives the user no clue which
    of their N configured Gmail/Calendar accounts is broken — they'd have to
    grep logs for the underlying refresh-token env-var name.
    """

    def test_alert_includes_account_email_when_known(self) -> None:
        _runtime_alert._last_alert_at = 0.0
        _runtime_alert.set_account_emails(["rovik@majiq.agency", "rovik@cantina.ai"])
        sent: list[str] = []
        _runtime_alert.set_send_telegram(lambda msg: sent.append(msg))
        try:
            _runtime_alert.runtime_oauth_alert(Exception("invalid_grant"), account_index=2)
        finally:
            _runtime_alert.set_send_telegram(None)  # type: ignore[arg-type]
            _runtime_alert.set_account_emails([])

        assert len(sent) == 1
        assert "rovik@cantina.ai" in sent[0]
        assert "account 2" in sent[0]

    def test_alert_falls_back_to_index_when_email_unknown(self) -> None:
        _runtime_alert._last_alert_at = 0.0
        _runtime_alert.set_account_emails([])  # nothing configured
        sent: list[str] = []
        _runtime_alert.set_send_telegram(lambda msg: sent.append(msg))
        try:
            _runtime_alert.runtime_oauth_alert(Exception("invalid_grant"), account_index=2)
        finally:
            _runtime_alert.set_send_telegram(None)  # type: ignore[arg-type]

        assert len(sent) == 1
        assert "account 2" in sent[0]

    def test_alert_no_account_label_when_index_omitted(self) -> None:
        """Single-account users (or callers that don't track index) still work."""
        _runtime_alert._last_alert_at = 0.0
        sent: list[str] = []
        _runtime_alert.set_send_telegram(lambda msg: sent.append(msg))
        try:
            _runtime_alert.runtime_oauth_alert(Exception("invalid_grant"))
        finally:
            _runtime_alert.set_send_telegram(None)  # type: ignore[arg-type]

        assert len(sent) == 1
        assert "account" not in sent[0].lower() or "Run:" in sent[0]


class TestRuntimeAlertWiring:
    """Regression: set_send_telegram must be called from production startup.

    The bug: set_send_telegram() existed and worked in unit tests (where the
    global was set directly), but was never invoked from app code. Every
    runtime OAuth failure logged "no Telegram configured" instead of paging
    the user, even though the bot was running.
    """

    def test_app_run_wires_runtime_alert(self) -> None:
        """app/_core.py's run() must call set_send_telegram after building send_telegram."""
        import inspect

        from cosinabox.app import _core

        src = inspect.getsource(_core)
        assert "set_send_telegram" in src, (
            "app/_core.py does not call set_send_telegram(). "
            "Runtime OAuth failures will not page Telegram. "
            "Add: from cosinabox.tools.google._runtime_alert import set_send_telegram; "
            "set_send_telegram(send_telegram)."
        )


class TestGmailRuntimeOAuthAlert:
    def test_refresh_error_sends_telegram_alert(self) -> None:
        """list_recent raising RefreshError -> send_telegram called with auth alert."""
        _reset_alert_state()
        service = MagicMock()
        service.users().messages().list().execute.side_effect = RefreshError("token expired")
        gmail = GmailTool(service=service)

        with patch("cosinabox.tools.google.gmail._runtime_oauth_alert") as mock_alert:
            result = gmail.list_recent()

        mock_alert.assert_called_once()
        assert result == []

    def test_search_refresh_error_returns_empty(self) -> None:
        """search() raising RefreshError -> graceful empty result."""
        _reset_alert_state()
        service = MagicMock()
        service.users().messages().list().execute.side_effect = RefreshError("token expired")
        gmail = GmailTool(service=service)

        with patch("cosinabox.tools.google.gmail._runtime_oauth_alert"):
            result = gmail.search("test query")

        assert result == []
