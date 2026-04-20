# ruff: noqa: I001
"""Tests for the keep_warm_* agent-facing tools."""

from __future__ import annotations

from unittest.mock import MagicMock

from cosinabox.tools.attio import KeepWarmPerson
from cosinabox.tools.registry import _build_attio_handlers


def test_all_three_keep_warm_handlers_registered() -> None:
    attio = MagicMock()
    handlers = _build_attio_handlers(attio)
    assert "keep_warm_set" in handlers
    assert "keep_warm_unset" in handlers
    assert "keep_warm_list" in handlers


# ---------------------------------------------------------------------------
# set
# ---------------------------------------------------------------------------


def test_keep_warm_set_happy_path() -> None:
    attio = MagicMock()
    attio.set_keep_warm.return_value = {
        "status": "ok",
        "record_id": "r1",
        "person": "Sarah Chen",
        "cadence_days": 14,
    }
    h = _build_attio_handlers(attio)
    out = h["keep_warm_set"](person="Sarah Chen", cadence_days=14, note="Lead investor")
    assert "Sarah Chen" in out
    assert "cadence: 14d" in out
    attio.set_keep_warm.assert_called_once_with(
        person="Sarah Chen", cadence_days=14, note="Lead investor"
    )


def test_keep_warm_set_person_not_found_returns_error_string() -> None:
    attio = MagicMock()
    attio.set_keep_warm.return_value = {
        "status": "error",
        "message": "Person 'Ghost' not found in Attio.",
    }
    h = _build_attio_handlers(attio)
    out = h["keep_warm_set"](person="Ghost", cadence_days=14)
    assert "failed" in out
    assert "Ghost" in out


def test_keep_warm_set_wraps_exceptions() -> None:
    attio = MagicMock()
    attio.set_keep_warm.side_effect = RuntimeError("httpx boom")
    h = _build_attio_handlers(attio)
    out = h["keep_warm_set"](person="x", cadence_days=14)
    assert "failed" in out
    assert "httpx boom" in out


# ---------------------------------------------------------------------------
# unset
# ---------------------------------------------------------------------------


def test_keep_warm_unset_happy_path() -> None:
    attio = MagicMock()
    attio.unset_keep_warm.return_value = {
        "status": "ok",
        "record_id": "r1",
        "person": "Sarah Chen",
    }
    h = _build_attio_handlers(attio)
    out = h["keep_warm_unset"](person="Sarah Chen", note="deprioritized")
    assert "Removed" in out
    assert "Sarah Chen" in out


def test_keep_warm_unset_person_not_found() -> None:
    attio = MagicMock()
    attio.unset_keep_warm.return_value = {"status": "error", "message": "Person 'Ghost' not found."}
    h = _build_attio_handlers(attio)
    out = h["keep_warm_unset"](person="Ghost")
    assert "failed" in out


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def _kwp(name: str, days: int | None, cadence: int = 14, note: str | None = None) -> KeepWarmPerson:
    return KeepWarmPerson(
        name=name,
        record_id="r",
        cadence_days=cadence,
        note=note,
        last_interaction=None if days is None else "2026-03-01T00:00:00Z",
        days_since=days,
    )


def test_keep_warm_list_empty() -> None:
    attio = MagicMock()
    attio.list_keep_warm.return_value = []
    h = _build_attio_handlers(attio)
    out = h["keep_warm_list"]()
    assert "No one" in out


def test_keep_warm_list_formats_rows_with_most_overdue_first() -> None:
    attio = MagicMock()
    attio.list_keep_warm.return_value = [
        _kwp("Tom", days=45, cadence=14),
        _kwp("Sarah", days=10, cadence=30, note="Lead"),
        _kwp("Unknown", days=None, cadence=60),
    ]
    h = _build_attio_handlers(attio)
    out = h["keep_warm_list"]()
    # Header
    assert "3 Keep Warm people" in out
    # Each name shown
    assert "Tom" in out
    assert "Sarah" in out
    assert "Unknown" in out
    # Note surfaces when present
    assert "Lead" in out
    # Unknown days rendered gracefully
    assert "no last contact on record" in out


def test_keep_warm_list_wraps_exceptions() -> None:
    attio = MagicMock()
    attio.list_keep_warm.side_effect = RuntimeError("api down")
    h = _build_attio_handlers(attio)
    out = h["keep_warm_list"]()
    assert "failed" in out
