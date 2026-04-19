# ruff: noqa: I001
"""Tests for followup_reminder: should honor recent outbound email as
fresh contact, not just the stakeholders.yaml ``last_contact`` field.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

from cosinabox.jobs.followup_reminder import FollowupReminderJob


def _today() -> date:
    return date(2026, 4, 18)


def _stakeholders() -> list[dict]:
    return [
        {
            "name": "Sarah Chen",
            "role": "Lead Investor",
            "cadence": "weekly",
            "email": "sarah@sequoia.example",
            # 45 days since manual yaml update, but gmail may have fresher signal.
            "last_contact": "2026-03-04",
        },
    ]


def _msg_on(day: date) -> MagicMock:
    m = MagicMock()
    m.id = day.isoformat()
    m.date = day.strftime("%a, %d %b %Y 10:00:00 +0000")
    m.sender = "Me <me@x.com>"
    m.subject = "Catching up"
    return m


# ---------------------------------------------------------------------------


def test_suppresses_when_recent_sent_mail_within_cadence() -> None:
    """Yaml says 45d ago — stale. But gmail shows mail to stakeholder
    yesterday. Weekly cadence + 14d staleness buffer = 21d threshold.
    Yesterday's mail wins → suppress."""
    gmail = MagicMock()
    gmail.search.return_value = [_msg_on(_today() - timedelta(days=1))]

    job = FollowupReminderJob(
        stakeholders=_stakeholders(),
        gmail=gmail,
        today=_today(),
    )
    assert job.run(None) == ""  # empty = no reminder sent


def test_fires_when_yaml_and_gmail_both_stale() -> None:
    """Yaml says 45d ago. Gmail shows last contact 30d ago. Weekly +
    14d = 21d threshold. Max(45, 30) = 30d stale → fire."""
    gmail = MagicMock()
    gmail.search.return_value = [_msg_on(_today() - timedelta(days=30))]

    job = FollowupReminderJob(
        stakeholders=_stakeholders(),
        gmail=gmail,
        today=_today(),
    )
    out = job.run(None)
    assert "Sarah Chen" in out


def test_fires_when_no_recent_sent_mail() -> None:
    """Gmail empty + yaml 45d ago + weekly cadence → fire."""
    gmail = MagicMock()
    gmail.search.return_value = []

    job = FollowupReminderJob(
        stakeholders=_stakeholders(),
        gmail=gmail,
        today=_today(),
    )
    out = job.run(None)
    assert "Sarah Chen" in out


def test_no_email_field_falls_back_to_yaml_only() -> None:
    """Stakeholder with no email field — behaves exactly like before."""
    gmail = MagicMock()
    gmail.search.return_value = [_msg_on(_today() - timedelta(days=1))]  # would be irrelevant

    stakeholders = [
        {
            "name": "Old Entry",
            "role": "Board",
            "cadence": "weekly",
            "last_contact": "2026-03-04",  # 45d ago
        },
    ]
    job = FollowupReminderJob(
        stakeholders=stakeholders,
        gmail=gmail,
        today=_today(),
    )
    # Gmail should NOT have been consulted for this stakeholder.
    out = job.run(None)
    gmail.search.assert_not_called()
    assert "Old Entry" in out


def test_no_gmail_client_preserves_legacy_behavior() -> None:
    """No gmail plumbed — job falls back to yaml-only (pre-PR behavior)."""
    job = FollowupReminderJob(
        stakeholders=_stakeholders(),
        gmail=None,
        today=_today(),
    )
    out = job.run(None)
    assert "Sarah Chen" in out


def test_uses_freshest_signal_between_yaml_and_gmail() -> None:
    """Yaml: 45d ago. Gmail: 5d ago. Weekly + 14d = 21d threshold.
    Freshest (5d) < threshold → suppress."""
    gmail = MagicMock()
    gmail.search.return_value = [_msg_on(_today() - timedelta(days=5))]

    job = FollowupReminderJob(
        stakeholders=_stakeholders(),
        gmail=gmail,
        today=_today(),
    )
    assert job.run(None) == ""
