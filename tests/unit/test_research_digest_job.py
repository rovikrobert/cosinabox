from __future__ import annotations

import textwrap
from types import SimpleNamespace

import pytest

from cosinabox.jobs.base import JobContext
from cosinabox.jobs.research_digest import ResearchDigestJob
from cosinabox.memory import Memory

CONFIG = textwrap.dedent(
    """
    schema_version: 1
    groups:
      - name: labs
        priority: 0
        search: {country: us, topic: news, time_range: week}
        entities:
          - name: Org Alpha
            queries: ["Org Alpha launch"]
    feeds: []
    field_queries: []
    """
)

SYNTH = {
    "telegram_summary": "Org Alpha shipped a thing.",
    "full_report": "# Report",
    "signal_records": [
        {"headline": "Org Alpha shipped", "source_url": "https://x/1", "entity": "Org Alpha"}
    ],
    "follow_up_signals": [],
}


@pytest.fixture
def wired(tmp_path, monkeypatch):
    (tmp_path / "research.yaml").write_text(CONFIG)
    mem = Memory(db_path=tmp_path / "memory.db")
    sent: list[str] = []

    monkeypatch.setattr(
        "cosinabox.jobs.research_digest.collect",
        lambda cfg, **kw: SimpleNamespace(
            items=[{"title": "T", "url": "https://x/1", "snippet": "", "source": "x"}],
            search_failed=False,
            counts={"raw": 1, "capped": 1},
        ),
    )
    monkeypatch.setattr("cosinabox.jobs.research_digest.classify", lambda items, **kw: items)
    monkeypatch.setattr(
        "cosinabox.jobs.research_digest.synthesize",
        lambda cfg, **kw: (dict(SYNTH), "{}"),
    )

    job = ResearchDigestJob(
        config_dir=tmp_path,
        db=mem,
        anthropic_client=SimpleNamespace(),
        search_api_key="k",
        send_telegram=sent.append,
        notify_error=sent.append,
        model="claude-sonnet-5",
    )
    return job, mem, sent


def test_missing_config_reports_not_configured(tmp_path):
    job = ResearchDigestJob(
        config_dir=tmp_path,
        db=None,
        anthropic_client=SimpleNamespace(),
        search_api_key="k",
        send_telegram=lambda m: None,
        notify_error=lambda m: None,
        model="m",
    )
    result = job.run(JobContext())
    assert "not configured" in result.lower()


def test_missing_api_key_reports_not_configured(tmp_path):
    (tmp_path / "research.yaml").write_text(CONFIG)
    job = ResearchDigestJob(
        config_dir=tmp_path,
        db=None,
        anthropic_client=SimpleNamespace(),
        search_api_key="",
        send_telegram=lambda m: None,
        notify_error=lambda m: None,
        model="m",
    )
    assert "not configured" in job.run(JobContext()).lower()


def test_happy_path_sends_summary_and_persists_signals(wired):
    job, mem, sent = wired
    result = job.run(JobContext())

    assert any("Org Alpha shipped a thing." in m for m in sent)
    assert "1 signal" in result
    # Signals and the dedup index both persisted.
    week = job._week_of()
    assert mem.research_signal_count(week_of=week) == 1
    assert [e["url"] for e in mem.load_research_dedup(now=job._now(), ttl_days=30, cap=10)] == [
        "https://x/1"
    ]


def test_total_search_failure_notifies_and_does_not_synthesize(tmp_path, monkeypatch):
    (tmp_path / "research.yaml").write_text(CONFIG)
    monkeypatch.setattr(
        "cosinabox.jobs.research_digest.collect",
        lambda cfg, **kw: SimpleNamespace(items=[], search_failed=True, counts={"raw": 0}),
    )

    def _must_not_run(*a, **kw):
        raise AssertionError("synthesis must not run without candidates")

    monkeypatch.setattr("cosinabox.jobs.research_digest.synthesize", _must_not_run)
    errors: list[str] = []
    job = ResearchDigestJob(
        config_dir=tmp_path,
        db=Memory(db_path=tmp_path / "m.db"),
        anthropic_client=SimpleNamespace(),
        search_api_key="k",
        send_telegram=lambda m: None,
        notify_error=errors.append,
        model="m",
    )
    result = job.run(JobContext())
    assert errors and "search" in errors[0].lower()
    assert "no candidates" in result.lower()


def test_alerts_are_routed_to_notify_error(tmp_path, monkeypatch):
    (tmp_path / "research.yaml").write_text(CONFIG)
    monkeypatch.setattr(
        "cosinabox.jobs.research_digest.collect",
        lambda cfg, **kw: SimpleNamespace(
            items=[{"title": "T", "url": "https://x/1"}], search_failed=False, counts={}
        ),
    )
    monkeypatch.setattr("cosinabox.jobs.research_digest.classify", lambda items, **kw: items)
    monkeypatch.setattr(
        "cosinabox.jobs.research_digest.synthesize",
        lambda cfg, **kw: ({**SYNTH, "signal_records": []}, "{}"),
    )
    errors: list[str] = []
    job = ResearchDigestJob(
        config_dir=tmp_path,
        db=Memory(db_path=tmp_path / "m.db"),
        anthropic_client=SimpleNamespace(),
        search_api_key="k",
        send_telegram=lambda m: None,
        notify_error=errors.append,
        model="m",
    )
    job.run(JobContext())
    # Zero signals must page, not pass silently.
    assert errors and "0 signals" in errors[0]
