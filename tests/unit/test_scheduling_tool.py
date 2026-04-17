"""Unit tests for scheduling tool definitions + handlers + policy rules."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from cosinabox.agent.policy import DEFAULT_RULES, Decision
from cosinabox.scheduling.models import SchedulingRequest, SchedulingStatus
from cosinabox.tools.scheduling_tool import (
    build_scheduling_handlers,
    build_scheduling_tool_definitions,
)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


class TestToolDefinitions:
    def test_returns_three_tools(self):
        defs = build_scheduling_tool_definitions(owner_name="Taylor")
        names = [d["name"] for d in defs]
        assert names == [
            "schedule_group_meeting",
            "scheduling_status",
            "scheduling_respond",
        ]

    def test_owner_name_interpolated_not_hardcoded(self):
        defs = build_scheduling_tool_definitions(owner_name="Taylor")
        # All three descriptions should mention Taylor (the provided owner)
        for d in defs:
            assert "Taylor" in d["description"], (
                f"{d['name']} description missing owner_name: {d['description']}"
            )
        # And definitely not "Rovik"
        for d in defs:
            assert "Rovik" not in d["description"]

    def test_schedule_group_meeting_schema(self):
        defs = build_scheduling_tool_definitions(owner_name="Taylor")
        sched = defs[0]
        required = sched["input_schema"]["required"]
        assert "title" in required
        assert "duration_minutes" in required
        assert "participants" in required
        assert "date_range_start" in required
        assert "date_range_end" in required

    def test_scheduling_respond_actions(self):
        defs = build_scheduling_tool_definitions(owner_name="Taylor")
        respond = defs[2]
        actions = respond["input_schema"]["properties"]["action"]["enum"]
        for expected in ("approve", "reject", "book", "cancel", "rework"):
            assert expected in actions


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _make_handlers():
    from cosinabox.scheduling.context import OwnerProfile, SchedulingContext

    db = MagicMock()
    ctx = SchedulingContext(
        db=db,
        owner=OwnerProfile(name="Taylor", timezone="Europe/Berlin"),
        gmail=MagicMock(),
        bot=MagicMock(),
        anthropic_client=MagicMock(),
        cost_tracker=MagicMock(),
    )
    return build_scheduling_handlers(ctx), db


class TestHandlersRegistered:
    def test_all_three_handlers(self):
        handlers, _ = _make_handlers()
        assert set(handlers.keys()) == {
            "schedule_group_meeting",
            "scheduling_status",
            "scheduling_respond",
        }


class TestScheduleGroupMeetingHandler:
    def test_calls_coordinator_start_scheduling(self):
        handlers, db = _make_handlers()

        fake_req = SchedulingRequest(
            id="abc123def456",
            title="Sync",
            duration_minutes=30,
            date_range_start=date(2026, 5, 1),
            date_range_end=date(2026, 5, 7),
            status=SchedulingStatus.OWNER_REVIEW.value,
        )
        fake_req.slots = []

        with patch(
            "cosinabox.tools.scheduling_tool.sched_coordinator.start_scheduling",
            return_value=fake_req,
        ) as mock_start:
            result = handlers["schedule_group_meeting"](
                title="Sync",
                duration_minutes=30,
                participants=[{"name": "Alice", "timezone": "UTC"}],
                date_range_start="2026-05-01",
                date_range_end="2026-05-07",
            )
            mock_start.assert_called_once()
            kwargs = mock_start.call_args.kwargs
            assert kwargs["owner_name"] == "Taylor"
            assert kwargs["owner_timezone"] == "Europe/Berlin"
            assert kwargs["duration_minutes"] == 30
            assert len(kwargs["participants"]) == 1

        assert "abc123def456" in result
        assert "owner_review" in result

    def test_empty_participants_rejected(self):
        handlers, _ = _make_handlers()
        result = handlers["schedule_group_meeting"](
            title="X",
            duration_minutes=30,
            participants=[],
            date_range_start="2026-05-01",
            date_range_end="2026-05-07",
        )
        assert "No participants" in result

    def test_invalid_date_rejected(self):
        handlers, _ = _make_handlers()
        result = handlers["schedule_group_meeting"](
            title="X",
            duration_minutes=30,
            participants=[{"name": "Alice"}],
            date_range_start="not-a-date",
            date_range_end="2026-05-07",
        )
        assert "Invalid date" in result


class TestSchedulingStatusHandler:
    def test_lists_active_requests_when_no_id(self):
        handlers, db = _make_handlers()
        req = SchedulingRequest(
            id="abc",
            title="T",
            duration_minutes=30,
            date_range_start=date(2026, 5, 1),
            date_range_end=date(2026, 5, 2),
            status="polling",
        )
        with patch(
            "cosinabox.tools.scheduling_tool.sched_db.get_active_requests",
            return_value=[req],
        ) as mock_active:
            result = handlers["scheduling_status"]()
            mock_active.assert_called_once()
            assert "1 active" in result
            assert "polling" in result

    def test_detail_when_id_supplied(self):
        handlers, db = _make_handlers()
        req = SchedulingRequest(
            id="abc",
            title="Sync",
            duration_minutes=30,
            date_range_start=date(2026, 5, 1),
            date_range_end=date(2026, 5, 2),
            status="polling",
        )
        with (
            patch(
                "cosinabox.tools.scheduling_tool.sched_db.get_request",
                return_value=req,
            ),
            patch(
                "cosinabox.tools.scheduling_tool.sched_db.get_responses",
                return_value=[],
            ),
        ):
            result = handlers["scheduling_status"](request_id="abc")
            assert "Sync" in result
            assert "polling" in result

    def test_not_found(self):
        handlers, _ = _make_handlers()
        with patch(
            "cosinabox.tools.scheduling_tool.sched_db.get_request",
            return_value=None,
        ):
            result = handlers["scheduling_status"](request_id="missing")
            assert "not found" in result


class TestSchedulingRespondHandler:
    def test_calls_coordinator_record_decision(self):
        handlers, _ = _make_handlers()
        with patch(
            "cosinabox.tools.scheduling_tool.sched_coordinator.record_decision",
            return_value={"status": "ok", "action": "approve", "new_status": "polling"},
        ) as mock_rd:
            result = handlers["scheduling_respond"](
                request_id="abc",
                action="approve",
            )
            mock_rd.assert_called_once()
            args, kwargs = mock_rd.call_args
            assert args[1] == "abc"
            assert args[2] == "approve"
            assert kwargs["owner_name"] == "Taylor"
            assert kwargs["owner_timezone"] == "Europe/Berlin"
        assert "polling" in result

    def test_book_includes_phase_b_caveat(self):
        handlers, _ = _make_handlers()
        with patch(
            "cosinabox.tools.scheduling_tool.sched_coordinator.record_decision",
            return_value={"status": "ok", "action": "book", "new_status": "booked"},
        ):
            result = handlers["scheduling_respond"](
                request_id="abc",
                action="book",
                slot_id=7,
            )
        assert "Plan 5" in result
        assert "manually" in result.lower()
        assert "calendar" in result.lower()

    def test_error_result_surfaced(self):
        handlers, _ = _make_handlers()
        with patch(
            "cosinabox.tools.scheduling_tool.sched_coordinator.record_decision",
            return_value={"status": "error", "reason": "wrong state"},
        ):
            result = handlers["scheduling_respond"](
                request_id="abc",
                action="approve",
            )
        assert "rejected" in result.lower()
        assert "wrong state" in result


# ---------------------------------------------------------------------------
# Policy rules
# ---------------------------------------------------------------------------


class TestPolicyRules:
    @pytest.mark.parametrize(
        "tool_name",
        [
            "schedule_group_meeting",
            "scheduling_status",
        ],
    )
    def test_rule_exists_priority_200_allow(self, tool_name):
        matches = [r for r in DEFAULT_RULES if r.tool_pattern == tool_name]
        assert len(matches) == 1, (
            f"Expected exactly one default rule for {tool_name}, got {len(matches)}"
        )
        rule = matches[0]
        assert rule.action == Decision.ALLOW
        assert rule.priority == 200

    def test_scheduling_respond_has_conditional_approve_rule(self) -> None:
        """scheduling_respond splits into a conditional REQUIRE_APPROVAL for
        action=approve (because it triggers outreach) and a default ALLOW for
        reject/cancel (local-only state changes)."""
        matches = [r for r in DEFAULT_RULES if r.tool_pattern == "scheduling_respond"]
        assert len(matches) == 2
        conditional = [r for r in matches if r.condition_field == "action"]
        default = [r for r in matches if r.condition_field == ""]
        assert len(conditional) == 1 and len(default) == 1
        assert conditional[0].action == Decision.REQUIRE_APPROVAL
        assert conditional[0].condition_value == "approve"
        assert default[0].action == Decision.ALLOW
        assert conditional[0].priority < default[0].priority
