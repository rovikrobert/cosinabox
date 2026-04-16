"""Tests for the policy engine — approval gates for tool execution."""

from __future__ import annotations

from cosinabox.agent.policy import (
    Decision,
    clear_approvals,
    evaluate,
    grant_temporary_approval,
    invalidate_cache,
)


def setup_function() -> None:
    """Reset state between tests."""
    clear_approvals()
    invalidate_cache()


# ---------------------------------------------------------------------------
# TTL alignment
# ---------------------------------------------------------------------------


class TestSchedulingRespondPolicy:
    """scheduling_respond('approve') triggers outreach → must require approval.
    Other actions ('reject', 'cancel') only change local state and stay ALLOW."""

    def test_approve_action_requires_approval(self) -> None:
        result = evaluate(
            "scheduling_respond",
            {"action": "approve", "request_id": "r1"},
        )
        assert result.decision == Decision.REQUIRE_APPROVAL

    def test_reject_action_is_allowed(self) -> None:
        result = evaluate(
            "scheduling_respond",
            {"action": "reject", "request_id": "r1"},
        )
        assert result.decision == Decision.ALLOW

    def test_cancel_action_is_allowed(self) -> None:
        result = evaluate(
            "scheduling_respond",
            {"action": "cancel", "request_id": "r1"},
        )
        assert result.decision == Decision.ALLOW


class TestTTLAlignment:
    def test_approval_ttl_matches_pending_tool_window(self) -> None:
        """Approval tokens must not expire before the user's reply window."""
        from cosinabox.agent.policy import _APPROVAL_TTL_S

        # app.py _PENDING_TOOL_TTL_S is 300; approvals must last at least as long
        # so a user approving at t=4min doesn't hit an already-expired token.
        assert _APPROVAL_TTL_S >= 300


# ---------------------------------------------------------------------------
# Default rules
# ---------------------------------------------------------------------------


class TestDefaultRules:
    def test_read_tools_are_allowed(self) -> None:
        for tool in [
            "gmail_search", "gmail_list_recent",
            "calendar_list_events", "calendar_find_conflicts",
            "calendar_find_free_time",
            "crm_search_people", "crm_get_person", "crm_list_people",
            "fireflies_list_meetings", "fireflies_get_transcript",
            "web_search",
        ]:
            result = evaluate(tool, {})
            assert result.decision == Decision.ALLOW, f"{tool} should be ALLOW"

    def test_draft_tools_are_allowed(self) -> None:
        result = evaluate("gmail_compose", {"to": "x@y.com", "subject": "Hi", "body": "Hey"})
        assert result.decision == Decision.ALLOW

        result = evaluate("gmail_draft_reply", {"message_id": "m1", "body": "Thanks"})
        assert result.decision == Decision.ALLOW

    def test_send_requires_approval(self) -> None:
        result = evaluate("gmail_send", {"draft_id": "d1"})
        assert result.decision == Decision.REQUIRE_APPROVAL

    def test_calendar_create_requires_approval(self) -> None:
        result = evaluate("calendar_create_event", {
            "summary": "Lunch", "start": "2026-04-14T12:00:00", "end": "2026-04-14T13:00:00",
        })
        assert result.decision == Decision.REQUIRE_APPROVAL

    def test_unknown_tool_requires_approval(self) -> None:
        result = evaluate("some_new_dangerous_tool", {"data": "whatever"})
        assert result.decision == Decision.REQUIRE_APPROVAL


# ---------------------------------------------------------------------------
# Temporary approvals
# ---------------------------------------------------------------------------


class TestTemporaryApprovals:
    def test_grant_and_consume(self) -> None:
        grant_temporary_approval("s1", "gmail_send")
        result = evaluate("gmail_send", {"draft_id": "d1"}, session_id="s1")
        assert result.decision == Decision.ALLOW
        assert "Temporary approval" in result.description

    def test_one_shot_consumed(self) -> None:
        grant_temporary_approval("s1", "gmail_send")
        # First use consumes it
        evaluate("gmail_send", {"draft_id": "d1"}, session_id="s1")
        # Second use falls back to rules
        result = evaluate("gmail_send", {"draft_id": "d1"}, session_id="s1")
        assert result.decision == Decision.REQUIRE_APPROVAL

    def test_session_isolation(self) -> None:
        grant_temporary_approval("s1", "gmail_send")
        # Different session doesn't get the approval
        result = evaluate("gmail_send", {"draft_id": "d1"}, session_id="s2")
        assert result.decision == Decision.REQUIRE_APPROVAL

    def test_tool_name_specificity(self) -> None:
        grant_temporary_approval("s1", "gmail_send")
        # Different tool doesn't get the approval
        result = evaluate("calendar_create_event", {"summary": "X"}, session_id="s1")
        assert result.decision == Decision.REQUIRE_APPROVAL


# ---------------------------------------------------------------------------
# Custom rules
# ---------------------------------------------------------------------------


class TestCustomRules:
    def test_custom_deny_rule(self) -> None:
        custom = [{
            "tool_pattern": "gmail_send",
            "action": "deny",
            "priority": 10,
            "description": "No email sending allowed",
        }]
        result = evaluate("gmail_send", {"draft_id": "d1"}, custom_rules=custom)
        assert result.decision == Decision.DENY

    def test_custom_allow_overrides_default(self) -> None:
        custom = [{
            "tool_pattern": "gmail_send",
            "action": "allow",
            "priority": 50,
            "description": "Auto-approve email sends",
        }]
        result = evaluate("gmail_send", {"draft_id": "d1"}, custom_rules=custom)
        assert result.decision == Decision.ALLOW

    def test_condition_field_matching(self) -> None:
        custom = [{
            "tool_pattern": "gmail_send",
            "action": "deny",
            "condition_field": "draft_id",
            "condition_op": "eq",
            "condition_value": "blocked-draft",
            "priority": 10,
            "description": "Block specific draft",
        }]
        # Matching condition
        result = evaluate("gmail_send", {"draft_id": "blocked-draft"}, custom_rules=custom)
        assert result.decision == Decision.DENY

        # Non-matching condition falls through
        invalidate_cache()
        result = evaluate("gmail_send", {"draft_id": "other"}, custom_rules=custom)
        assert result.decision == Decision.REQUIRE_APPROVAL  # default rule

    def test_condition_contains(self) -> None:
        custom = [{
            "tool_pattern": "gmail_compose",
            "action": "deny",
            "condition_field": "to",
            "condition_op": "contains",
            "condition_value": ".gov",
            "priority": 10,
            "description": "Block government emails",
        }]
        result = evaluate("gmail_compose", {"to": "official@agency.gov.sg"}, custom_rules=custom)
        assert result.decision == Decision.DENY

        invalidate_cache()
        result = evaluate("gmail_compose", {"to": "friend@gmail.com"}, custom_rules=custom)
        assert result.decision == Decision.ALLOW  # default allows drafts


# ---------------------------------------------------------------------------
# PolicyResult structure
# ---------------------------------------------------------------------------


class TestPolicyResult:
    def test_result_includes_tool_name(self) -> None:
        result = evaluate("gmail_search", {})
        assert result.tool_name == "gmail_search"

    def test_result_includes_description(self) -> None:
        result = evaluate("gmail_send", {"draft_id": "d1"})
        assert result.description  # not empty


# ---------------------------------------------------------------------------
# Integration: policy in AgentLoop
# ---------------------------------------------------------------------------


class TestPolicyInAgentLoop:
    def test_allowed_tool_executes(self) -> None:
        from unittest.mock import MagicMock

        from cosinabox.agent.cost import CostTracker
        from cosinabox.agent.loop import AgentLoop
        from cosinabox.agent.routing import Router

        mock_client = MagicMock()

        # First response: tool_use for gmail_search (ALLOW)
        tool_response = MagicMock()
        tool_response.stop_reason = "tool_use"
        tool_response.usage.input_tokens = 100
        tool_response.usage.output_tokens = 50
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "gmail_search"
        tool_block.input = {"query": "test"}
        tool_block.id = "t1"
        tool_response.content = [tool_block]

        # Second response: end_turn
        end_response = MagicMock()
        end_response.stop_reason = "end_turn"
        end_response.usage.input_tokens = 200
        end_response.usage.output_tokens = 100
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Found 3 emails."
        end_response.content = [text_block]

        mock_client.messages.create.side_effect = [tool_response, end_response]

        def fake_search(query: str, max_results: int = 10) -> str:
            return '["email1", "email2"]'

        loop = AgentLoop(
            anthropic_client=mock_client,
            router=Router(),
            cost_tracker=CostTracker(per_message_cap_usd=1.0, daily_cap_usd=10.0),
            tools={"gmail_search": fake_search},
            tool_definitions=[{
                "name": "gmail_search",
                "description": "test",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            }],
            system_prompt="Test",
        )

        result = loop.run(prompt="search email", session_id="test")
        assert result.final_text == "Found 3 emails."
        assert result.tool_calls[0].name == "gmail_search"
        assert "BLOCKED" not in result.tool_calls[0].result
        assert "APPROVAL" not in result.tool_calls[0].result

    def test_blocked_tool_returns_approval_required(self) -> None:
        from unittest.mock import MagicMock

        from cosinabox.agent.cost import CostTracker
        from cosinabox.agent.loop import AgentLoop
        from cosinabox.agent.routing import Router

        mock_client = MagicMock()

        # Response: tool_use for gmail_send (REQUIRE_APPROVAL)
        tool_response = MagicMock()
        tool_response.stop_reason = "tool_use"
        tool_response.usage.input_tokens = 100
        tool_response.usage.output_tokens = 50
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "gmail_send"
        tool_block.input = {"draft_id": "d1"}
        tool_block.id = "t1"
        tool_response.content = [tool_block]

        # Claude responds to the APPROVAL REQUIRED with text
        end_response = MagicMock()
        end_response.stop_reason = "end_turn"
        end_response.usage.input_tokens = 200
        end_response.usage.output_tokens = 100
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "I need your approval to send this email."
        end_response.content = [text_block]

        mock_client.messages.create.side_effect = [tool_response, end_response]

        loop = AgentLoop(
            anthropic_client=mock_client,
            router=Router(),
            cost_tracker=CostTracker(per_message_cap_usd=1.0, daily_cap_usd=10.0),
            tools={"gmail_send": lambda draft_id: "sent"},
            tool_definitions=[{
                "name": "gmail_send",
                "description": "test",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            }],
            system_prompt="Test",
        )

        result = loop.run(prompt="send the email", session_id="test")
        # The tool should NOT have been executed
        assert "APPROVAL REQUIRED" in result.tool_calls[0].result

    def test_multi_tool_response_holds_all_if_any_blocked(self) -> None:
        """If Claude sends compose (ALLOW) + send (REQUIRE_APPROVAL),
        NEITHER should execute."""
        from unittest.mock import MagicMock

        from cosinabox.agent.cost import CostTracker
        from cosinabox.agent.loop import AgentLoop
        from cosinabox.agent.routing import Router

        mock_client = MagicMock()

        # Response with TWO tool_use blocks: compose (ALLOW) + send (REQUIRE_APPROVAL)
        tool_response = MagicMock()
        tool_response.stop_reason = "tool_use"
        tool_response.usage.input_tokens = 100
        tool_response.usage.output_tokens = 50

        compose_block = MagicMock()
        compose_block.type = "tool_use"
        compose_block.name = "gmail_compose"
        compose_block.input = {"to": "a@b.com", "subject": "Hi", "body": "Hey"}
        compose_block.id = "t1"

        send_block = MagicMock()
        send_block.type = "tool_use"
        send_block.name = "gmail_send"
        send_block.input = {"draft_id": "d1"}
        send_block.id = "t2"

        tool_response.content = [compose_block, send_block]

        end_response = MagicMock()
        end_response.stop_reason = "end_turn"
        end_response.usage.input_tokens = 200
        end_response.usage.output_tokens = 100
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "I need approval."
        end_response.content = [text_block]

        mock_client.messages.create.side_effect = [tool_response, end_response]

        compose_called = []
        send_called = []

        loop = AgentLoop(
            anthropic_client=mock_client,
            router=Router(),
            cost_tracker=CostTracker(per_message_cap_usd=1.0, daily_cap_usd=10.0),
            tools={
                "gmail_compose": lambda **kw: compose_called.append(1) or "drafted",
                "gmail_send": lambda **kw: send_called.append(1) or "sent",
            },
            tool_definitions=[
                {
                    "name": "gmail_compose",
                    "description": "test",
                    "input_schema": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
                {
                    "name": "gmail_send",
                    "description": "test",
                    "input_schema": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            ],
            system_prompt="Test",
        )

        result = loop.run(prompt="compose and send", session_id="test")

        # NEITHER tool should have executed
        assert compose_called == [], "gmail_compose should NOT execute when batch has blocked tools"
        assert send_called == [], "gmail_send should NOT execute"
        # compose should be HELD, send should be APPROVAL REQUIRED
        assert "HELD" in result.tool_calls[0].result
        assert "APPROVAL REQUIRED" in result.tool_calls[1].result
