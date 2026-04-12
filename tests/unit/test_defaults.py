from __future__ import annotations

from cosinabox import defaults


def test_cost_caps_present() -> None:
    assert defaults.COST_PER_MESSAGE_CAP_USD == 0.75
    assert defaults.COST_DAILY_CAP_USD == 15.00


def test_tool_loop_limits_present() -> None:
    assert defaults.MAX_TOOL_ITERATIONS == 8
    assert defaults.TOOL_ITERATION_DELAY_S == 2.0


def test_summarization_threshold_present() -> None:
    assert defaults.CONVERSATION_SUMMARIZE_THRESHOLD == 25


def test_pre_meeting_window_present() -> None:
    assert defaults.PRE_MEETING_PREP_MINUTES_BEFORE == 30
    assert defaults.PRE_MEETING_PREP_WINDOW_MINUTES == 5


def test_followup_threshold_present() -> None:
    assert defaults.FOLLOWUP_STALENESS_DAYS == 14


def test_conversation_retention_present() -> None:
    assert defaults.CONVERSATION_RETENTION_DAYS == 30
