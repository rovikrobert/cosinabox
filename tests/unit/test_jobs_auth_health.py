from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from google.auth.exceptions import RefreshError, TransportError

from cosinabox.jobs.auth_health import AuthHealthJob
from cosinabox.jobs.base import JobContext
from cosinabox.tools.google.auth import GoogleAuthError


def _healthy_cred() -> MagicMock:
    c = MagicMock()
    c.refresh.return_value = None
    return c


def _broken_cred() -> MagicMock:
    c = MagicMock()
    c.refresh.side_effect = RefreshError("invalid_grant: revoked")
    return c


def _transient_cred() -> MagicMock:
    c = MagicMock()
    c.refresh.side_effect = TransportError("connection reset")
    return c


def _factory(creds_or_exc):
    def factory():
        if isinstance(creds_or_exc, BaseException):
            raise creds_or_exc
        return list(creds_or_exc)

    return factory


def test_no_creds_configured_returns_empty():
    job = AuthHealthJob(credentials_factory=_factory(GoogleAuthError("not set")))
    assert job.run(JobContext()) == ""
    assert job._health == {}


def test_single_healthy_cred_returns_empty():
    job = AuthHealthJob(credentials_factory=_factory([_healthy_cred()]))
    assert job.run(JobContext()) == ""
    assert job._health == {1: True}


def test_single_broken_cred_emits_failure_text():
    job = AuthHealthJob(credentials_factory=_factory([_broken_cred()]))
    out = job.run(JobContext())
    assert "Google auth failed for account #1" in out
    assert "cosinabox auth google" in out
    assert "GOOGLE_OAUTH_REFRESH_TOKEN_1" in out
    assert job._health == {1: False}


def test_still_broken_on_second_tick_is_silent():
    c = _broken_cred()
    job = AuthHealthJob(credentials_factory=_factory([c]))
    first = job.run(JobContext())
    second = job.run(JobContext())
    assert "failed" in first
    assert second == ""


def test_recovery_emits_restored_text():
    broken = _broken_cred()
    healthy = _healthy_cred()
    creds = [broken]
    job = AuthHealthJob(credentials_factory=lambda: list(creds))
    assert "failed" in job.run(JobContext())
    creds[0] = healthy
    out = job.run(JobContext())
    assert "Google auth restored for account #1" in out


def test_transport_error_does_not_change_state():
    broken = _broken_cred()
    transient = _transient_cred()
    healthy = _healthy_cred()
    creds = [broken]
    job = AuthHealthJob(credentials_factory=lambda: list(creds))

    assert "failed" in job.run(JobContext())
    assert job._health == {1: False}

    creds[0] = transient
    assert job.run(JobContext()) == ""
    assert job._health == {1: False}

    creds[0] = healthy
    assert "restored" in job.run(JobContext())
    assert job._health == {1: True}


def test_two_creds_one_fails_one_healthy():
    job = AuthHealthJob(credentials_factory=_factory([_healthy_cred(), _broken_cred()]))
    out = job.run(JobContext())
    assert "account #2" in out
    assert "account #1" not in out
    assert job._health == {1: True, 2: False}


def test_both_failing_and_recovering_in_same_tick():
    broken1 = _broken_cred()
    healthy2 = _healthy_cred()
    creds = [broken1, healthy2]
    job = AuthHealthJob(credentials_factory=lambda: list(creds))

    assert "account #1" in job.run(JobContext())
    assert job._health == {1: False, 2: True}

    creds[0] = _healthy_cred()
    creds[1] = _broken_cred()
    out = job.run(JobContext())
    assert "Google auth failed for account #2" in out
    assert "Google auth restored for account #1" in out


def test_restart_re_alerts_still_broken():
    cred = _broken_cred()
    job1 = AuthHealthJob(credentials_factory=_factory([cred]))
    first = job1.run(JobContext())
    assert "failed" in first

    cred2 = _broken_cred()
    job2 = AuthHealthJob(credentials_factory=_factory([cred2]))
    assert "failed" in job2.run(JobContext())


def test_return_includes_fix_instructions():
    job = AuthHealthJob(credentials_factory=_factory([_broken_cred()]))
    out = job.run(JobContext())
    assert "Fix:" in out
    assert "cosinabox auth google" in out
    assert "Railway" in out


@pytest.mark.parametrize(
    "exc",
    [
        Exception("unknown"),
        ValueError("bad config"),
        OSError("network down"),
    ],
)
def test_unknown_exception_treated_like_transport_error(exc):
    """Non-RefreshError exceptions preserve prior state, don't flap."""
    cred = MagicMock()
    cred.refresh.side_effect = exc
    job = AuthHealthJob(credentials_factory=_factory([cred]))
    assert job.run(JobContext()) == ""
    assert job._health == {}
