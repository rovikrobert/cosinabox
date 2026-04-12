from __future__ import annotations

from cosinabox.agent.routing import Router


def test_default_model_is_sonnet() -> None:
    router = Router()
    assert router.choose_model("what time is my next meeting?") == "claude-sonnet-4-6"


def test_strategic_keyword_routes_to_opus() -> None:
    router = Router()
    assert router.choose_model("Help me think through our hiring strategy") == "claude-opus-4-6"
    assert router.choose_model("Draft a board update") == "claude-opus-4-6"


def test_dm_mode_allows_full_tool_set() -> None:
    router = Router(available_tools={"gmail", "calendar", "web_search"})
    assert router.tools_for_channel("dm") == {"gmail", "calendar", "web_search"}


def test_group_mode_restricted_to_safe_subset() -> None:
    router = Router(available_tools={"gmail", "calendar", "web_search"})
    assert router.tools_for_channel("group") == {"calendar", "web_search"}
