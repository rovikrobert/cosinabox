"""Tests for Telegram bot command handlers."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cosinabox.bot.commands import (
    build_brief_handler,
    build_cost_handler,
    build_status_handler,
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
