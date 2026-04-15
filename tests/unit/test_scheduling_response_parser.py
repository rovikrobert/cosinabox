from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cosinabox.scheduling.models import TimeSlot
from cosinabox.scheduling.response_parser import (
    parse_callback_data,
    parse_response,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _slot(db_id: int, hour: int) -> TimeSlot:
    start = datetime(2026, 4, 20, hour, 0, tzinfo=timezone.utc)
    end = datetime(2026, 4, 20, hour + 1, 0, tzinfo=timezone.utc)
    return TimeSlot(start_time=start, end_time=end, db_id=db_id)


def _fake_client(text: str, *, input_tokens: int = 100, output_tokens: int = 50):
    """Build a mock anthropic client whose messages.create returns `text`."""
    content = [SimpleNamespace(text=text)]
    usage = SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    response = SimpleNamespace(content=content, usage=usage)

    client = MagicMock()
    client.messages.create.return_value = response
    return client


# ---------------------------------------------------------------------------
# parse_response — NL parsing
# ---------------------------------------------------------------------------


def test_parse_response_truncates_very_long_reply() -> None:
    """Adversarial or quoted-history replies must be capped before Sonnet."""
    slots = [_slot(10, 9)]
    client = _fake_client('{"responses": {"10": "yes"}}')
    huge_reply = "a" * 50_000

    parse_response(
        participant_name="Alice",
        slots=slots,
        reply_text=huge_reply,
        anthropic_client=client,
    )

    prompt_sent = client.messages.create.call_args.kwargs["messages"][0]["content"]
    # Prompt should not carry the full 50k payload; cap is well under 10k chars.
    assert len(prompt_sent) < 10_000


def test_parse_response_valid_json_returns_responses() -> None:
    slots = [_slot(10, 9), _slot(11, 14)]
    client = _fake_client(
        '{"responses": {"10": "yes", "11": "no"}}'
    )

    out = parse_response(
        participant_name="Alice",
        slots=slots,
        reply_text="Morning works, afternoon no",
        anthropic_client=client,
    )

    assert out == {"responses": {"10": "yes", "11": "no"}}
    # Model id should be the cosinabox default (sonnet 4-6)
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-sonnet-4-6"


def test_parse_response_counter_proposal() -> None:
    slots = [_slot(1, 9)]
    client = _fake_client(
        '{"counter_proposal": "How about Friday afternoon instead?"}'
    )

    out = parse_response(
        participant_name="Bob",
        slots=slots,
        reply_text="None of those work, Friday afternoon?",
        anthropic_client=client,
    )

    assert out == {"counter_proposal": "How about Friday afternoon instead?"}


def test_parse_response_strips_markdown_code_fence() -> None:
    slots = [_slot(7, 10)]
    client = _fake_client(
        '```json\n{"responses": {"7": "yes"}}\n```'
    )

    out = parse_response(
        participant_name="Carol",
        slots=slots,
        reply_text="Yes slot 1 works.",
        anthropic_client=client,
    )

    assert out == {"responses": {"7": "yes"}}


def test_parse_response_malformed_json_returns_error() -> None:
    slots = [_slot(1, 9)]
    client = _fake_client("not json at all {{{")

    out = parse_response(
        participant_name="Dan",
        slots=slots,
        reply_text="???",
        anthropic_client=client,
    )

    assert "error" in out
    assert "parse" in out["error"].lower() or "could not" in out["error"].lower()


def test_parse_response_api_exception_returns_error() -> None:
    slots = [_slot(1, 9)]
    client = MagicMock()
    client.messages.create.side_effect = RuntimeError("boom")

    out = parse_response(
        participant_name="Eve",
        slots=slots,
        reply_text="hi",
        anthropic_client=client,
    )

    assert "error" in out
    assert "boom" in out["error"]


def test_parse_response_records_cost_when_tracker_provided() -> None:
    slots = [_slot(1, 9)]
    client = _fake_client(
        '{"responses": {"1": "yes"}}',
        input_tokens=1000,
        output_tokens=200,
    )
    tracker = MagicMock()

    out = parse_response(
        participant_name="Frank",
        slots=slots,
        reply_text="yes",
        anthropic_client=client,
        cost_tracker=tracker,
    )

    assert "responses" in out
    tracker.record.assert_called_once()
    # Positional cost arg should be a positive float (sonnet pricing > 0).
    (call_cost,) = tracker.record.call_args.args
    assert call_cost > 0


def test_parse_response_records_cost_even_on_malformed_json() -> None:
    """We paid the API — record the spend regardless of JSON validity."""
    slots = [_slot(1, 9)]
    client = _fake_client("garbage", input_tokens=50, output_tokens=10)
    tracker = MagicMock()

    out = parse_response(
        participant_name="Gina",
        slots=slots,
        reply_text="hm",
        anthropic_client=client,
        cost_tracker=tracker,
    )

    assert "error" in out
    tracker.record.assert_called_once()


def test_parse_response_no_tracker_does_not_crash() -> None:
    slots = [_slot(1, 9)]
    client = _fake_client('{"responses": {"1": "yes"}}')

    out = parse_response(
        participant_name="Hal",
        slots=slots,
        reply_text="yes",
        anthropic_client=client,
        cost_tracker=None,
    )

    assert out == {"responses": {"1": "yes"}}


# ---------------------------------------------------------------------------
# parse_callback_data — no LLM
# ---------------------------------------------------------------------------


def test_callback_valid_single_slot() -> None:
    out = parse_callback_data("sched_resp:abc-123:5:10")
    assert out == {
        "request_id": "abc-123",
        "participant_db_id": 5,
        "slot_ids": [10],
    }


def test_callback_valid_multi_slot_comma_list() -> None:
    out = parse_callback_data("sched_resp:req-1:3:10,20,30")
    assert out == {
        "request_id": "req-1",
        "participant_db_id": 3,
        "slot_ids": [10, 20, 30],
    }


def test_callback_wrong_prefix() -> None:
    out = parse_callback_data("approve:something:1:2")
    assert "error" in out


def test_callback_too_few_parts() -> None:
    out = parse_callback_data("sched_resp:abc")
    assert "error" in out


def test_callback_too_many_parts() -> None:
    out = parse_callback_data("sched_resp:abc:1:2:3")
    assert "error" in out


def test_callback_non_integer_participant_id() -> None:
    out = parse_callback_data("sched_resp:abc:notanumber:10")
    assert "error" in out


def test_callback_non_integer_slot_id() -> None:
    out = parse_callback_data("sched_resp:abc:1:notaslot")
    assert "error" in out


def test_callback_empty_string() -> None:
    out = parse_callback_data("")
    assert "error" in out


def test_callback_non_string_input() -> None:
    out = parse_callback_data(None)  # type: ignore[arg-type]
    assert "error" in out


def test_callback_empty_slot_list() -> None:
    out = parse_callback_data("sched_resp:abc:1:")
    assert "error" in out
