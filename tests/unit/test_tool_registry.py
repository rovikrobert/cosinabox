"""Tests for the tool registry — definitions, handlers, and AgentLoop wiring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import MagicMock

from cosinabox.tools.registry import (
    ATTIO_TOOL_DEFINITIONS,
    CALENDAR_TOOL_DEFINITIONS,
    FIREFLIES_TOOL_DEFINITIONS,
    GMAIL_TOOL_DEFINITIONS,
    WEB_SEARCH_TOOL_DEFINITIONS,
    _serialize,
    build_tool_registry,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class FakeEmail:
    id: str
    sender: str
    subject: str
    snippet: str
    date: str


@dataclass
class FakeEvent:
    id: str
    summary: str
    start: datetime
    end: datetime


def _make_gmail() -> MagicMock:
    gmail = MagicMock()
    gmail.search.return_value = [
        FakeEmail("m1", "alice@x.com", "Hello", "Hi there", "2026-04-12"),
    ]
    gmail.list_recent.return_value = [
        FakeEmail("m2", "bob@x.com", "Update", "FYI", "2026-04-12"),
    ]
    return gmail


def _make_calendar() -> MagicMock:
    cal = MagicMock()
    cal.list_events.return_value = [
        FakeEvent(
            "e1",
            "Standup",
            datetime(2026, 4, 12, 9, 0, tzinfo=UTC),
            datetime(2026, 4, 12, 9, 30, tzinfo=UTC),
        ),
    ]
    cal.find_conflicts.return_value = []
    return cal


def _make_attio() -> MagicMock:
    attio = MagicMock()
    attio.search_people.return_value = [{"id": "p1", "name": "Alice", "role": "CEO"}]
    attio.get_person.return_value = {"id": "p1", "name": "Alice", "role": "CEO"}
    attio.list_people.return_value = [{"id": "p1", "name": "Alice", "role": "CEO"}]
    return attio


def _make_fireflies() -> MagicMock:
    ff = MagicMock()
    ff.list_recent_meetings.return_value = [{"id": "t1", "title": "Sync", "date": "2026-04-12"}]
    ff.get_transcript.return_value = {"id": "t1", "title": "Sync", "sentences": []}
    return ff


def _make_web_search() -> MagicMock:
    ws = MagicMock()
    ws.search.return_value = [{"title": "Result 1", "link": "https://example.com"}]
    return ws


# ---------------------------------------------------------------------------
# build_tool_registry tests
# ---------------------------------------------------------------------------


class TestBuildToolRegistry:
    def test_empty_instances_returns_empty(self) -> None:
        defs, handlers = build_tool_registry({})
        assert defs == []
        assert handlers == {}

    def test_gmail_only(self) -> None:
        defs, handlers = build_tool_registry({"gmail": _make_gmail()})
        assert len(defs) == len(GMAIL_TOOL_DEFINITIONS)
        assert set(handlers.keys()) == {
            "gmail_search",
            "gmail_list_recent",
            "gmail_compose",
            "gmail_send",
        }

    def test_calendar_only(self) -> None:
        defs, handlers = build_tool_registry({"calendar": _make_calendar()})
        assert len(defs) == len(CALENDAR_TOOL_DEFINITIONS)
        assert set(handlers.keys()) == {
            "calendar_list_events",
            "calendar_find_conflicts",
            "calendar_create_event",
            "calendar_find_free_time",
        }

    def test_attio_only(self) -> None:
        defs, handlers = build_tool_registry({"attio": _make_attio()})
        assert len(defs) == len(ATTIO_TOOL_DEFINITIONS)
        assert set(handlers.keys()) == {
            "crm_search_people",
            "crm_get_person",
            "crm_list_people",
            "keep_warm_set",
            "keep_warm_unset",
            "keep_warm_list",
        }

    def test_all_tools(self) -> None:
        instances = {
            "gmail": _make_gmail(),
            "calendar": _make_calendar(),
            "attio": _make_attio(),
            "fireflies": _make_fireflies(),
            "web_search": _make_web_search(),
        }
        defs, handlers = build_tool_registry(instances)
        expected_count = (
            len(GMAIL_TOOL_DEFINITIONS)
            + len(CALENDAR_TOOL_DEFINITIONS)
            + len(ATTIO_TOOL_DEFINITIONS)
            + len(FIREFLIES_TOOL_DEFINITIONS)
            + len(WEB_SEARCH_TOOL_DEFINITIONS)
        )
        assert len(defs) == expected_count
        assert len(handlers) == expected_count

    def test_definition_handler_names_match(self) -> None:
        """Every definition has a matching handler, no orphans."""
        instances = {
            "gmail": _make_gmail(),
            "calendar": _make_calendar(),
            "attio": _make_attio(),
            "fireflies": _make_fireflies(),
            "web_search": _make_web_search(),
        }
        defs, handlers = build_tool_registry(instances)
        def_names = {d["name"] for d in defs}
        assert def_names == set(handlers.keys())

    def test_definitions_have_required_fields(self) -> None:
        """All tool definitions have name, description, and input_schema."""
        instances = {
            "gmail": _make_gmail(),
            "calendar": _make_calendar(),
            "attio": _make_attio(),
            "fireflies": _make_fireflies(),
            "web_search": _make_web_search(),
        }
        defs, _ = build_tool_registry(instances)
        for d in defs:
            assert "name" in d, f"Missing 'name' in {d}"
            assert "description" in d, f"Missing 'description' in {d.get('name')}"
            assert "input_schema" in d, f"Missing 'input_schema' in {d.get('name')}"
            schema = d["input_schema"]
            assert schema["type"] == "object"
            assert "properties" in schema
            assert "required" in schema

    def test_no_hardcoded_user_names_in_descriptions(self) -> None:
        """OSS-friendly: no hardcoded names like 'Rovik' in tool descriptions."""
        instances = {
            "gmail": _make_gmail(),
            "calendar": _make_calendar(),
            "attio": _make_attio(),
            "fireflies": _make_fireflies(),
            "web_search": _make_web_search(),
        }
        defs, _ = build_tool_registry(instances)
        forbidden = ["rovik", "cantina", "majiq"]
        for d in defs:
            desc_lower = d["description"].lower()
            for word in forbidden:
                assert (
                    word not in desc_lower
                ), f"Tool '{d['name']}' description contains '{word}' — not OSS-friendly"


# ---------------------------------------------------------------------------
# Handler execution tests
# ---------------------------------------------------------------------------


class TestHandlerExecution:
    def test_gmail_search_calls_tool(self) -> None:
        gmail = _make_gmail()
        _, handlers = build_tool_registry({"gmail": gmail})
        result = handlers["gmail_search"](query="test", max_results=5)
        gmail.search.assert_called_once_with("test", max_results=5)
        assert "alice@x.com" in result

    def test_gmail_list_recent_calls_tool(self) -> None:
        gmail = _make_gmail()
        _, handlers = build_tool_registry({"gmail": gmail})
        result = handlers["gmail_list_recent"](hours=12, max_results=10)
        gmail.list_recent.assert_called_once_with(hours=12, max_results=10)
        assert "bob@x.com" in result

    def test_calendar_list_events_parses_iso(self) -> None:
        cal = _make_calendar()
        _, handlers = build_tool_registry({"calendar": cal})
        result = handlers["calendar_list_events"](
            start="2026-04-12T00:00:00+08:00",
            end="2026-04-12T23:59:00+08:00",
        )
        cal.list_events.assert_called_once()
        args = cal.list_events.call_args
        assert isinstance(args.kwargs["start"], datetime)
        assert "Standup" in result

    def test_calendar_find_conflicts_no_conflicts(self) -> None:
        cal = _make_calendar()
        _, handlers = build_tool_registry({"calendar": cal})
        result = handlers["calendar_find_conflicts"](
            start="2026-04-12T10:00:00+08:00",
            end="2026-04-12T11:00:00+08:00",
        )
        assert result == "No conflicts found."

    def test_crm_get_person_found(self) -> None:
        attio = _make_attio()
        _, handlers = build_tool_registry({"attio": attio})
        result = handlers["crm_get_person"](name="Alice")
        attio.get_person.assert_called_once_with("Alice")
        assert "Alice" in result

    def test_crm_get_person_not_found(self) -> None:
        attio = _make_attio()
        attio.get_person.return_value = None
        _, handlers = build_tool_registry({"attio": attio})
        result = handlers["crm_get_person"](name="Nobody")
        assert "No person found" in result

    def test_web_search_caps_num(self) -> None:
        ws = _make_web_search()
        _, handlers = build_tool_registry({"web_search": ws})
        handlers["web_search"](query="test", num=20)
        ws.search.assert_called_once_with("test", num=10)

    def test_fireflies_list_meetings(self) -> None:
        ff = _make_fireflies()
        _, handlers = build_tool_registry({"fireflies": ff})
        result = handlers["fireflies_list_meetings"](hours=48)
        ff.list_recent_meetings.assert_called_once_with(hours=48)
        assert "Sync" in result

    def test_calendar_create_event_success(self) -> None:
        cal = _make_calendar()
        created = FakeEvent(
            "new-1",
            "Team Sync",
            datetime(2026, 4, 14, 14, 0, tzinfo=UTC),
            datetime(2026, 4, 14, 15, 0, tzinfo=UTC),
        )
        cal.create_event.return_value = created
        _, handlers = build_tool_registry({"calendar": cal})
        result = handlers["calendar_create_event"](
            summary="Team Sync",
            start="2026-04-14T14:00:00+00:00",
            end="2026-04-14T15:00:00+00:00",
        )
        assert "Event created" in result
        assert "Team Sync" in result
        cal.create_event.assert_called_once()

    def test_calendar_create_event_conflict(self) -> None:
        from cosinabox.tools.google.calendar import CalendarConflict

        cal = _make_calendar()
        conflicts = [
            FakeEvent(
                "e1",
                "Standup",
                datetime(2026, 4, 14, 14, 0, tzinfo=UTC),
                datetime(2026, 4, 14, 14, 30, tzinfo=UTC),
            )
        ]
        cal.create_event.side_effect = CalendarConflict(conflicts)
        _, handlers = build_tool_registry({"calendar": cal})
        result = handlers["calendar_create_event"](
            summary="Coffee",
            start="2026-04-14T14:00:00+00:00",
            end="2026-04-14T15:00:00+00:00",
        )
        assert "CONFLICT" in result
        assert "Standup" in result

    def test_calendar_find_free_time_returns_slots(self) -> None:
        cal = _make_calendar()
        cal.find_free_time.return_value = [
            (
                datetime(2026, 4, 14, 9, 0, tzinfo=UTC),
                datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
            ),
            (
                datetime(2026, 4, 14, 11, 0, tzinfo=UTC),
                datetime(2026, 4, 14, 22, 0, tzinfo=UTC),
            ),
        ]
        _, handlers = build_tool_registry({"calendar": cal})
        result = handlers["calendar_find_free_time"](
            date="2026-04-14",
            duration_minutes=30,
        )
        assert "09:00" in result
        assert "Available slots" in result

    def test_calendar_find_free_time_no_slots(self) -> None:
        cal = _make_calendar()
        cal.find_free_time.return_value = []
        _, handlers = build_tool_registry({"calendar": cal})
        result = handlers["calendar_find_free_time"](
            date="2026-04-14",
            duration_minutes=60,
        )
        assert "No available slots" in result


# ---------------------------------------------------------------------------
# AgentLoop tool_definitions wiring test
# ---------------------------------------------------------------------------


class TestAgentLoopToolDefinitions:
    def test_loop_passes_tool_definitions_to_api(self) -> None:
        """AgentLoop sends tool_definitions in the Claude API call."""
        from cosinabox.agent.cost import CostTracker
        from cosinabox.agent.loop import AgentLoop
        from cosinabox.agent.routing import Router

        mock_client = MagicMock()
        # Simulate an end_turn response (no tool use)
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        mock_response.content = [text_block]
        mock_client.messages.create.return_value = mock_response

        fake_defs = [
            {
                "name": "test_tool",
                "description": "A test tool",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            }
        ]

        loop = AgentLoop(
            anthropic_client=mock_client,
            router=Router(),
            cost_tracker=CostTracker(per_message_cap_usd=1.0, daily_cap_usd=10.0),
            tools={},
            tool_definitions=fake_defs,
            system_prompt="You are a test.",
        )

        result = loop.run(prompt="hi", session_id="test")
        assert result.final_text == "Hello!"

        # Verify tools were passed in the API call
        call_kwargs = mock_client.messages.create.call_args
        assert "tools" in call_kwargs.kwargs or "tools" in (
            call_kwargs[1] if len(call_kwargs) > 1 else {}
        )
        # Access via kwargs
        passed_tools = call_kwargs.kwargs.get("tools") or call_kwargs[1].get("tools")
        assert passed_tools == fake_defs

    def test_loop_without_definitions_omits_tools_key(self) -> None:
        """AgentLoop with no tool_definitions doesn't send tools param."""
        from cosinabox.agent.cost import CostTracker
        from cosinabox.agent.loop import AgentLoop
        from cosinabox.agent.routing import Router

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"
        mock_response.content = [text_block]
        mock_client.messages.create.return_value = mock_response

        loop = AgentLoop(
            anthropic_client=mock_client,
            router=Router(),
            cost_tracker=CostTracker(per_message_cap_usd=1.0, daily_cap_usd=10.0),
            tools={},
            system_prompt="You are a test.",
        )

        loop.run(prompt="hi", session_id="test")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "tools" not in call_kwargs


# ---------------------------------------------------------------------------
# Timezone handling tests
# ---------------------------------------------------------------------------


class TestTimezoneHandling:
    def test_find_free_time_uses_configured_timezone(self) -> None:
        """Handler uses the timezone passed to build_tool_registry, not UTC."""
        from zoneinfo import ZoneInfo

        cal = _make_calendar()
        cal.find_free_time.return_value = [
            (
                datetime(2026, 4, 14, 9, 0, tzinfo=ZoneInfo("Asia/Singapore")),
                datetime(2026, 4, 14, 12, 0, tzinfo=ZoneInfo("Asia/Singapore")),
            ),
        ]
        _, handlers = build_tool_registry(
            {"calendar": cal},
            timezone="Asia/Singapore",
        )
        handlers["calendar_find_free_time"](
            date="2026-04-14",
            duration_minutes=30,
        )
        # Verify the datetime passed to CalendarTool has SGT timezone
        call_args = cal.find_free_time.call_args
        passed_date = call_args.kwargs["date"]
        assert passed_date.tzinfo is not None
        assert str(passed_date.tzinfo) == "Asia/Singapore"

    def test_find_free_time_defaults_to_utc(self) -> None:
        """Without explicit timezone, handler uses UTC."""

        cal = _make_calendar()
        cal.find_free_time.return_value = []
        _, handlers = build_tool_registry({"calendar": cal})
        handlers["calendar_find_free_time"](
            date="2026-04-14",
            duration_minutes=30,
        )
        call_args = cal.find_free_time.call_args
        passed_date = call_args.kwargs["date"]
        assert str(passed_date.tzinfo) == "UTC"


# ---------------------------------------------------------------------------
# _serialize edge case tests
# ---------------------------------------------------------------------------


class TestSerializeEdgeCases:
    def test_serialize_empty_list(self) -> None:
        assert _serialize([]) == "[]"

    def test_serialize_empty_dict(self) -> None:
        assert _serialize({}) == "{}"

    def test_serialize_string_passthrough(self) -> None:
        assert _serialize("hello") == "hello"

    def test_serialize_none_in_list(self) -> None:
        result = _serialize([None, "foo"])
        assert "null" in result
        assert "foo" in result

    def test_serialize_dataclass_in_dict_values(self) -> None:
        """Dataclass values in dicts are properly serialized, not repr'd."""
        result = _serialize(
            {
                "event": FakeEvent(
                    "e1",
                    "Standup",
                    datetime(2026, 4, 12, 9, 0, tzinfo=UTC),
                    datetime(2026, 4, 12, 9, 30, tzinfo=UTC),
                )
            }
        )
        assert "Standup" in result
        assert "FakeEvent" not in result  # Should not be repr()

    def test_serialize_single_dataclass(self) -> None:
        result = _serialize(
            FakeEvent(
                "e1",
                "Standup",
                datetime(2026, 4, 12, 9, 0, tzinfo=UTC),
                datetime(2026, 4, 12, 9, 30, tzinfo=UTC),
            )
        )
        assert "Standup" in result
        assert "e1" in result
