from __future__ import annotations

import json
from types import SimpleNamespace

from cosinabox.research.config import Entity, Group, ResearchConfig, SearchSpec
from cosinabox.research.synthesizer import (
    SYNTHESIS_FAILED_NOTICE,
    build_prompt,
    format_candidates,
    parse_response,
    synthesize,
)

CFG = ResearchConfig(
    groups=(
        Group(
            name="labs",
            priority=0,
            search=SearchSpec(),
            entities=(Entity(name="Org Alpha", aliases=("OrgA",)),),
        ),
    ),
    feeds=(),
    field_queries=(),
)

GOOD = {
    "telegram_summary": "One thing happened.",
    "full_report": "# Report\n\nDetail.",
    "signal_records": [{"headline": "H", "source_url": "https://x/1"}],
    "follow_up_signals": ["dig into H"],
}


def test_format_candidates_includes_source_date_title_and_url():
    text = format_candidates(
        [
            {
                "source": "x.com",
                "published": "2026-08-18",
                "title": "T",
                "snippet": "S",
                "url": "https://x/1",
            }
        ]
    )
    assert "[x.com]" in text and "(2026-08-18)" in text and "T" in text and "https://x/1" in text


def test_format_candidates_handles_an_empty_set():
    assert "No candidates" in format_candidates([])


def test_prompt_lists_tracked_entities_and_the_dedup_index():
    prompt = build_prompt(
        CFG,
        candidates="CAND",
        dedup_index=[{"headline": "Old news", "url": "https://x/0"}],
        week_of="2026-08-17",
    )
    assert "Org Alpha" in prompt
    assert "OrgA" in prompt
    assert "Old news" in prompt
    assert "2026-08-17" in prompt
    assert "CAND" in prompt


def test_prompt_says_first_run_when_the_index_is_empty():
    assert "first run" in build_prompt(CFG, candidates="C", dedup_index=[], week_of="w").lower()


def test_parse_accepts_clean_json():
    assert parse_response(json.dumps(GOOD)) == GOOD


def test_parse_accepts_fenced_json():
    parsed = parse_response(f"Sure:\n```json\n{json.dumps(GOOD)}\n```")
    assert parsed["telegram_summary"] == "One thing happened."


def test_parse_salvages_a_truncated_object():
    truncated = (
        json.dumps(GOOD)[: json.dumps(GOOD).index('"signal_records"')]
        + '"signal_records": [{"headline": "H"'
    )
    parsed = parse_response(truncated)
    # The fields that finished before the cut must survive.
    assert parsed["telegram_summary"] == "One thing happened."
    assert parsed["full_report"] == "# Report\n\nDetail."


def test_parse_fills_missing_keys():
    parsed = parse_response(json.dumps({"telegram_summary": "s"}))
    assert parsed["full_report"] == ""
    assert parsed["signal_records"] == []
    assert parsed["follow_up_signals"] == []


def test_parse_returns_the_failure_notice_on_garbage():
    parsed = parse_response("I could not comply.")
    assert parsed["telegram_summary"] == SYNTHESIS_FAILED_NOTICE
    assert parsed["signal_records"] == []


def test_synthesize_streams_and_returns_raw_text(monkeypatch):
    seen: dict[str, object] = {}

    def _fake_stream(client, model, *, system, messages, max_tokens, tools=None):
        seen.update({"model": model, "max_tokens": max_tokens, "tools": tools})
        return json.dumps(GOOD), model

    monkeypatch.setattr("cosinabox.research.synthesizer.call_with_failover_stream", _fake_stream)
    parsed, raw = synthesize(
        CFG,
        items=[{"title": "T", "url": "https://x/1"}],
        dedup_index=[],
        week_of="2026-08-17",
        client=SimpleNamespace(),
        model="claude-sonnet-5",
    )
    assert parsed["telegram_summary"] == "One thing happened."
    assert json.loads(raw) == GOOD
    # No tools: this is pure synthesis over pre-fetched data.
    assert seen["tools"] is None
    assert seen["max_tokens"] >= 32_000
