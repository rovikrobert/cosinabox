"""Tests for participant timezone + channel resolution."""

from __future__ import annotations

from cosinabox.scheduling.participant import resolve_channel, resolve_timezone


class TestResolveTimezone:
    def test_explicit_tz_wins(self):
        tz = resolve_timezone(
            email="alice@x.com",
            org="Acme",
            explicit_tz="Europe/Berlin",
            default_tz="UTC",
            domain_map={"x.com": "Asia/Tokyo"},
            org_map={"Acme": "America/Los_Angeles"},
        )
        assert tz == "Europe/Berlin"

    def test_explicit_tz_equal_to_default_falls_through(self):
        tz = resolve_timezone(
            email="alice@x.com",
            org=None,
            explicit_tz="UTC",
            default_tz="UTC",
            domain_map={"x.com": "Asia/Tokyo"},
        )
        assert tz == "Asia/Tokyo"

    def test_org_match(self):
        tz = resolve_timezone(
            email=None,
            org="Acme Corp Ltd",
            explicit_tz=None,
            default_tz="UTC",
            org_map={"acme": "America/Los_Angeles"},
        )
        assert tz == "America/Los_Angeles"

    def test_domain_match_exact(self):
        tz = resolve_timezone(
            email="alice@example.com",
            org=None,
            explicit_tz=None,
            default_tz="UTC",
            domain_map={"example.com": "America/New_York"},
        )
        assert tz == "America/New_York"

    def test_domain_match_subdomain(self):
        tz = resolve_timezone(
            email="alice@mail.example.com",
            org=None,
            explicit_tz=None,
            default_tz="UTC",
            domain_map={"example.com": "America/New_York"},
        )
        assert tz == "America/New_York"

    def test_fallback_to_default(self):
        tz = resolve_timezone(
            email="alice@unknown.com",
            org=None,
            explicit_tz=None,
            default_tz="Asia/Singapore",
        )
        assert tz == "Asia/Singapore"

    def test_empty_maps_no_crash(self):
        tz = resolve_timezone(
            email="alice@x.com",
            org="Acme",
            explicit_tz=None,
            default_tz="UTC",
        )
        assert tz == "UTC"

    def test_no_email_skips_domain(self):
        tz = resolve_timezone(
            email=None,
            org=None,
            explicit_tz=None,
            default_tz="UTC",
            domain_map={"x.com": "Asia/Tokyo"},
        )
        assert tz == "UTC"


class TestResolveChannel:
    def test_telegram_wins_when_id_present(self):
        assert resolve_channel(email="alice@x.com", telegram_id="12345") == "telegram"

    def test_gmail_when_only_email(self):
        assert resolve_channel(email="alice@x.com", telegram_id=None) == "gmail"

    def test_gmail_default_when_nothing_set(self):
        assert resolve_channel(email=None, telegram_id=None) == "gmail"
