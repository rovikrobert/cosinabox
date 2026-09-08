from __future__ import annotations

from cosinabox import defaults
from cosinabox.research.alerts import synthesis_alerts
from cosinabox.research.synthesizer import SYNTHESIS_FAILED_NOTICE

BUDGET = defaults.RESEARCH_SYNTHESIS_MAX_TOKENS * defaults.RESEARCH_SYNTHESIS_CHARS_PER_TOKEN


def test_healthy_run_produces_no_alerts():
    assert synthesis_alerts(telegram_summary="Real summary.", signal_count=4, raw_length=1000) == []


def test_failure_notice_alerts():
    alerts = synthesis_alerts(
        telegram_summary=SYNTHESIS_FAILED_NOTICE, signal_count=0, raw_length=42
    )
    assert len(alerts) == 1
    assert "no parseable output" in alerts[0]


def test_zero_signals_alerts_even_when_parsing_succeeded():
    alerts = synthesis_alerts(telegram_summary="Quiet week.", signal_count=0, raw_length=900)
    assert len(alerts) == 1
    assert "0 signals" in alerts[0]


def test_near_ceiling_alerts():
    alerts = synthesis_alerts(
        telegram_summary="Real summary.", signal_count=3, raw_length=int(BUDGET * 0.85)
    )
    assert len(alerts) == 1
    assert "ceiling" in alerts[0]


def test_failure_and_near_ceiling_both_reported():
    alerts = synthesis_alerts(
        telegram_summary=SYNTHESIS_FAILED_NOTICE,
        signal_count=0,
        raw_length=int(BUDGET * 0.95),
    )
    assert len(alerts) == 2


def test_failure_notice_and_zero_signals_do_not_double_report():
    # A failed parse always has 0 signals; reporting both would be noise.
    alerts = synthesis_alerts(
        telegram_summary=SYNTHESIS_FAILED_NOTICE, signal_count=0, raw_length=10
    )
    assert not any("0 signals" in a for a in alerts)
