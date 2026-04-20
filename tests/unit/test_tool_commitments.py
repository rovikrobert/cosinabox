# ruff: noqa: I001
"""Tests for the commitment_* agent-facing tools.

Every handler returns a string (never raises) so AgentLoop can inject it
into the conversation as tool_result content without special-casing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cosinabox.commitments import create_commitment
from cosinabox.memory import Memory
from cosinabox.tools.commitments_tool import (
    COMMITMENT_TOOL_DEFINITIONS,
    build_commitment_handlers,
)


@pytest.fixture
def handlers(tmp_path: Path) -> tuple[dict, Memory]:
    db = Memory(db_path=tmp_path / "test.db")
    return build_commitment_handlers(db), db


def test_all_tool_defs_have_handlers() -> None:
    def_names = {d["name"] for d in COMMITMENT_TOOL_DEFINITIONS}
    handler_names = set(build_commitment_handlers(None).keys())  # type: ignore[arg-type]
    assert def_names == handler_names


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


def test_create_happy_path(handlers) -> None:
    h, _ = handlers
    out = h["commitment_create"](title="send NTU deck", priority=1)
    assert out.startswith("Created")
    assert "send NTU deck" in out
    assert "P1" in out


def test_create_with_stakeholder_and_deadline(handlers) -> None:
    h, _ = handlers
    out = h["commitment_create"](
        title="follow up with Sarah",
        stakeholder="Sarah Chen",
        deadline="2026-05-01",
    )
    assert "Sarah Chen" in out
    assert "2026-05-01" in out


def test_create_invalid_source_soft_falls_back(handlers) -> None:
    """Unknown source string becomes 'manual' — the CRUD layer is forgiving."""
    h, _ = handlers
    out = h["commitment_create"](title="x", source="wat")
    assert out.startswith("Created")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_empty(handlers) -> None:
    h, _ = handlers
    out = h["commitment_list"]()
    assert "No commitments" in out


def test_list_open_items(handlers) -> None:
    h, db = handlers
    create_commitment(db, title="a")
    create_commitment(db, title="b")
    out = h["commitment_list"]()
    assert "2 commitment(s)" in out
    assert "a" in out
    assert "b" in out


def test_list_all_statuses(handlers) -> None:
    h, db = handlers
    a = create_commitment(db, title="open one")
    b = create_commitment(db, title="to close")
    h["commitment_close"](id=b["id"])

    out = h["commitment_list"](status="all")
    assert "open one" in out
    assert "to close" in out
    # Default call filters to open.
    open_only = h["commitment_list"]()
    assert "open one" in open_only
    assert "to close" not in open_only
    _ = a  # silence


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


def test_update_flips_status_and_reports_diff(handlers) -> None:
    h, db = handlers
    c = create_commitment(db, title="x")
    out = h["commitment_update"](id=c["id"], status="blocked")
    assert "blocked" in out
    assert f"#{c['id']}" in out


def test_update_missing_id_returns_error_string(handlers) -> None:
    h, _ = handlers
    out = h["commitment_update"](id=9999, status="done")
    assert "failed" in out
    assert "9999" in out


def test_update_unchanged_fields_reports_unchanged(handlers) -> None:
    h, db = handlers
    c = create_commitment(db, title="x")
    out = h["commitment_update"](id=c["id"])  # no fields
    assert "unchanged" in out


# ---------------------------------------------------------------------------
# close / dismiss / reopen
# ---------------------------------------------------------------------------


def test_close_moves_to_done(handlers) -> None:
    h, db = handlers
    c = create_commitment(db, title="x")
    out = h["commitment_close"](id=c["id"], reason="merged PR #42")
    assert "Closed" in out
    assert "done" in out


def test_close_twice_is_idempotent_error(handlers) -> None:
    h, db = handlers
    c = create_commitment(db, title="x")
    h["commitment_close"](id=c["id"])
    out = h["commitment_close"](id=c["id"])
    assert "already closed" in out.lower()


def test_dismiss_moves_to_cancelled(handlers) -> None:
    h, db = handlers
    c = create_commitment(db, title="x")
    out = h["commitment_dismiss"](id=c["id"], reason="priorities changed")
    assert "Dismissed" in out
    assert "cancelled" in out


def test_reopen_restores_open(handlers) -> None:
    h, db = handlers
    c = create_commitment(db, title="x")
    h["commitment_close"](id=c["id"])
    out = h["commitment_reopen"](id=c["id"])
    assert "Reopened" in out
    assert "open" in out


def test_reopen_not_closed_returns_error(handlers) -> None:
    h, db = handlers
    c = create_commitment(db, title="x")
    out = h["commitment_reopen"](id=c["id"])
    assert "failed" in out
