"""Tests for Telegram bot command handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cosinabox.bot.commands import (
    build_brief_handler,
    build_cost_handler,
    build_status_handler,
    build_timezone_handler,
    cmd_help,
)


def _fake_update() -> MagicMock:
    update = MagicMock()
    update.message = AsyncMock()
    update.message.reply_text = AsyncMock()
    return update


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cmd_help_lists_commands() -> None:
    update = _fake_update()
    await cmd_help(update, None)
    reply = update.message.reply_text.call_args[0][0]
    assert "/help" in reply
    assert "/status" in reply
    assert "/cost" in reply
    assert "/brief" in reply


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cmd_status_shows_config() -> None:
    handler = build_status_handler(
        name="Jamie",
        timezone="America/Los_Angeles",
        tool_definitions=[
            {"name": "gmail_search"},
            {"name": "calendar_list_events"},
        ],
        jobs_config={
            "morning_briefing": {"enabled": True, "schedule": "0 8 * * *"},
            "evening_wrap": {"enabled": False},
        },
        stakeholder_count=5,
    )
    update = _fake_update()
    await handler(update, None)
    reply = update.message.reply_text.call_args[0][0]
    assert "Jamie" in reply
    assert "America/Los_Angeles" in reply
    assert "2" in reply  # 2 tools
    assert "gmail_search" in reply
    assert "morning_briefing" in reply
    assert "evening_wrap" not in reply  # disabled
    assert "5" in reply  # stakeholder count


@pytest.mark.asyncio
async def test_cmd_status_empty_config() -> None:
    handler = build_status_handler(
        name="New User",
        timezone="UTC",
        tool_definitions=[],
        jobs_config={},
        stakeholder_count=0,
    )
    update = _fake_update()
    await handler(update, None)
    reply = update.message.reply_text.call_args[0][0]
    assert "none" in reply.lower()  # no tools or jobs


@pytest.mark.asyncio
async def test_cmd_status_renders_oauth_line_when_rows_exist(tmp_path) -> None:
    """When auth_health has persisted rows, /status appends an OAuth line
    showing per-account status with ✓/✗ markers and email labels.
    """
    from cosinabox.jobs.auth_health_persist import record_auth_health

    db = tmp_path / "memory.db"
    record_auth_health(db, account_index=1, email="rovik@majiq.agency", ok=True)
    record_auth_health(db, account_index=2, email="rovik@cantina.ai", ok=False)

    handler = build_status_handler(
        name="Rovik",
        timezone="Asia/Singapore",
        tool_definitions=[],
        jobs_config={},
        stakeholder_count=0,
        db_path=db,
    )
    update = _fake_update()
    await handler(update, None)
    reply = update.message.reply_text.call_args[0][0]

    assert "OAuth:" in reply
    assert "rovik@majiq.agency" in reply
    assert "rovik@cantina.ai" in reply
    assert "✓" in reply
    assert "✗" in reply


@pytest.mark.asyncio
async def test_cmd_status_omits_oauth_line_when_empty(tmp_path) -> None:
    """No persisted rows → no OAuth line. Don't show '(unknown)' noise on
    fresh deploys before the first auth_health tick.
    """
    db = tmp_path / "memory.db"  # File doesn't exist; persisted state empty.

    handler = build_status_handler(
        name="x",
        timezone="UTC",
        tool_definitions=[],
        jobs_config={},
        stakeholder_count=0,
        db_path=db,
    )
    update = _fake_update()
    await handler(update, None)
    reply = update.message.reply_text.call_args[0][0]
    assert "OAuth:" not in reply


@pytest.mark.asyncio
async def test_cmd_status_renders_oauth_line_for_single_account(tmp_path) -> None:
    """Single-account users see the OAuth line too — uniformity beats
    hiding the row (spec open question #2).
    """
    from cosinabox.jobs.auth_health_persist import record_auth_health

    db = tmp_path / "memory.db"
    record_auth_health(db, account_index=1, email="solo@example.com", ok=True)

    handler = build_status_handler(
        name="x",
        timezone="UTC",
        tool_definitions=[],
        jobs_config={},
        stakeholder_count=0,
        db_path=db,
    )
    update = _fake_update()
    await handler(update, None)
    reply = update.message.reply_text.call_args[0][0]
    assert "OAuth:" in reply
    assert "solo@example.com" in reply


# ---------------------------------------------------------------------------
# /cost
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cmd_cost_shows_today_spend() -> None:
    from cosinabox.agent.cost import CostTracker

    tracker = CostTracker(per_message_cap_usd=0.75, daily_cap_usd=15.0)
    tracker.record(2.50)  # record some spend today

    handler = build_cost_handler(cost_tracker=tracker)
    update = _fake_update()
    await handler(update, None)
    reply = update.message.reply_text.call_args[0][0]
    assert "$2.50" in reply
    assert "$15.00" in reply
    assert "17%" in reply  # 2.50/15.00 = 16.7% → 17%


@pytest.mark.asyncio
async def test_cmd_cost_zero_spend() -> None:
    from cosinabox.agent.cost import CostTracker

    tracker = CostTracker(per_message_cap_usd=0.75, daily_cap_usd=15.0)
    handler = build_cost_handler(cost_tracker=tracker)
    update = _fake_update()
    await handler(update, None)
    reply = update.message.reply_text.call_args[0][0]
    assert "$0.00" in reply


# ---------------------------------------------------------------------------
# /brief
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cmd_brief_runs_agent_loop() -> None:
    mock_loop = MagicMock()
    mock_result = MagicMock()
    mock_result.final_text = "Your top priority is shipping the feature."
    mock_loop.run.return_value = mock_result

    handler = build_brief_handler(agent_loop=mock_loop, chat_id="123")
    update = _fake_update()
    await handler(update, None)

    # Verify agent loop was called
    mock_loop.run.assert_called_once()
    call_kwargs = mock_loop.run.call_args.kwargs
    assert "brief" in call_kwargs["session_id"]
    assert "briefing" in call_kwargs["prompt"].lower()

    # Verify reply sent (2 calls: "Generating..." + actual reply)
    assert update.message.reply_text.call_count == 2
    final_reply = update.message.reply_text.call_args_list[1][0][0]
    assert "shipping the feature" in final_reply


@pytest.mark.asyncio
async def test_cmd_brief_handles_error() -> None:
    mock_loop = MagicMock()
    mock_loop.run.side_effect = RuntimeError("API down")

    handler = build_brief_handler(agent_loop=mock_loop, chat_id="123")
    update = _fake_update()
    await handler(update, None)

    # Should still reply with error message
    assert update.message.reply_text.call_count == 2
    final_reply = update.message.reply_text.call_args_list[1][0][0]
    assert "error" in final_reply.lower()


# ---------------------------------------------------------------------------
# /timezone — runtime tz change without redeploy
# ---------------------------------------------------------------------------


def _fake_context(args: list[str] | None = None) -> MagicMock:
    ctx = MagicMock()
    ctx.args = args or []
    return ctx


@pytest.mark.asyncio
async def test_cmd_timezone_no_args_shows_current(monkeypatch) -> None:
    """`/timezone` with no args shows the current TZ + local time."""
    from cosinabox import timezone as tz_mod

    monkeypatch.setattr(tz_mod, "_timezone", "Asia/Singapore")
    handler = build_timezone_handler(scheduler=MagicMock(), db_path=None)

    update = _fake_update()
    await handler(update, _fake_context([]))

    reply = update.message.reply_text.call_args[0][0]
    assert "Asia/Singapore" in reply
    assert "/timezone" in reply  # usage hint


@pytest.mark.asyncio
async def test_cmd_timezone_change_reschedules_jobs(monkeypatch, tmp_path) -> None:
    """`/timezone Asia/Tokyo` updates state, persists, and reschedules jobs."""
    from cosinabox import timezone as tz_mod

    monkeypatch.setattr(tz_mod, "_timezone", "Asia/Singapore")
    scheduler = MagicMock()
    scheduler.reschedule_all.return_value = 5
    db_path = tmp_path / "memory.db"
    handler = build_timezone_handler(scheduler=scheduler, db_path=db_path)

    update = _fake_update()
    await handler(update, _fake_context(["Asia/Tokyo"]))

    # Reschedule was called with the new TZ.
    scheduler.reschedule_all.assert_called_once_with("Asia/Tokyo")
    # In-memory state was updated.
    assert tz_mod.get_timezone() == "Asia/Tokyo"
    # Reply confirms the change.
    reply = update.message.reply_text.call_args[0][0]
    assert "Asia/Singapore" in reply  # old
    assert "Asia/Tokyo" in reply  # new
    assert "5" in reply  # rescheduled count
    # Persisted to disk.
    assert db_path.exists()


@pytest.mark.asyncio
async def test_cmd_timezone_invalid_does_not_change_state(monkeypatch) -> None:
    """`/timezone Fake/Zone` shows an error and leaves state untouched."""
    from cosinabox import timezone as tz_mod

    monkeypatch.setattr(tz_mod, "_timezone", "Asia/Singapore")
    scheduler = MagicMock()
    handler = build_timezone_handler(scheduler=scheduler, db_path=None)

    update = _fake_update()
    await handler(update, _fake_context(["Fake/Zone"]))

    # Scheduler not touched.
    scheduler.reschedule_all.assert_not_called()
    # State unchanged.
    assert tz_mod.get_timezone() == "Asia/Singapore"
    # Error reply.
    reply = update.message.reply_text.call_args[0][0]
    assert "Unknown" in reply or "Invalid" in reply or "unknown" in reply.lower()


@pytest.mark.asyncio
async def test_cmd_timezone_resolves_city_name(monkeypatch, tmp_path) -> None:
    """`/timezone Tokyo` resolves to Asia/Tokyo via the fuzzy matcher."""
    from cosinabox import timezone as tz_mod

    monkeypatch.setattr(tz_mod, "_timezone", "UTC")
    scheduler = MagicMock()
    scheduler.reschedule_all.return_value = 1
    handler = build_timezone_handler(scheduler=scheduler, db_path=tmp_path / "m.db")

    update = _fake_update()
    await handler(update, _fake_context(["Tokyo"]))

    scheduler.reschedule_all.assert_called_once_with("Asia/Tokyo")
    assert tz_mod.get_timezone() == "Asia/Tokyo"
