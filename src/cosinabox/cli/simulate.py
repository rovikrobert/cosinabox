"""`cosinabox simulate <job>` — local dry-run against a fixture."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import click
import yaml

from cosinabox import defaults
from cosinabox.agent.cost import CostTracker
from cosinabox.agent.loop import AgentLoop
from cosinabox.agent.routing import Router
from cosinabox.jobs.base import JobContext
from cosinabox.jobs.evening_wrap import EveningWrapJob
from cosinabox.jobs.followup_reminder import FollowupReminderJob
from cosinabox.jobs.morning_briefing import MorningBriefingJob
from cosinabox.jobs.pre_meeting_prep import PreMeetingPrepJob
from cosinabox.jobs.weekly_review import WeeklyReviewJob

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures"


@dataclass
class _StubMessage:
    id: str
    sender: str
    subject: str
    snippet: str
    date: str


@dataclass
class _StubEvent:
    id: str
    summary: str
    start: datetime
    end: datetime


class _StubGmail:
    def __init__(self, messages: list[_StubMessage]) -> None:
        self._msgs = messages

    def list_recent(self, *, hours: int = 24, max_results: int = 25) -> list[_StubMessage]:
        return self._msgs[:max_results]

    def search(self, query: str, *, max_results: int = 25) -> list[_StubMessage]:
        return self._msgs[:max_results]


class _StubCalendar:
    def __init__(self, events: list[_StubEvent]) -> None:
        self._events = events

    def list_events(self, *, start: datetime, end: datetime) -> list[_StubEvent]:
        return self._events


def _load_fixture(fixture: str) -> tuple[_StubGmail, _StubCalendar, list[dict]]:
    fdir = FIXTURE_ROOT / fixture
    msgs_raw = json.loads((fdir / "emails.json").read_text())
    events_raw = json.loads((fdir / "calendar_events.json").read_text())
    stakeholders = yaml.safe_load((fdir / "stakeholders.yaml").read_text())["stakeholders"]
    msgs = [_StubMessage(**m) for m in msgs_raw]
    events = [
        _StubEvent(
            id=e["id"],
            summary=e["summary"],
            start=datetime.fromisoformat(e["start"]),
            end=datetime.fromisoformat(e["end"]),
        )
        for e in events_raw
    ]
    return _StubGmail(msgs), _StubCalendar(events), stakeholders


def _build_agent_loop() -> AgentLoop:
    if os.getenv("ANTHROPIC_API_KEY"):
        from anthropic import Anthropic

        client: Any = Anthropic()
    else:
        client = MagicMock()
        fake_resp = MagicMock()
        fake_resp.stop_reason = "end_turn"
        fake_resp.content = [MagicMock(type="text", text="[mocked briefing output]")]
        fake_resp.usage.input_tokens = 0
        fake_resp.usage.output_tokens = 0
        client.messages.create.return_value = fake_resp
    return AgentLoop(
        anthropic_client=client,
        router=Router(),
        cost_tracker=CostTracker(
            per_message_cap_usd=defaults.COST_PER_MESSAGE_CAP_USD,
            daily_cap_usd=defaults.COST_DAILY_CAP_USD,
        ),
        tools={},
        max_tool_iterations=defaults.MAX_TOOL_ITERATIONS,
        tool_iteration_delay_s=0,  # no sleep in simulate
    )


def _load_personality(config_dir: Path) -> tuple[str, str]:
    import re

    text = (config_dir / "personality.md").read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return "(no personality)", "user"
    front = yaml.safe_load(m.group(1))
    body = m.group(2)
    return body, front.get("name", "user")


@click.command("simulate")
@click.argument("job_name")
@click.option("--fixture", default="sample", help="Fixture name under tests/fixtures/.")
@click.pass_context
def simulate_cmd(ctx: click.Context, job_name: str, fixture: str) -> None:
    """Run a job against a fixture and print what would be sent."""
    config_dir: Path = ctx.obj["config_dir"]
    gmail, calendar, stakeholders = _load_fixture(fixture)
    personality, name = _load_personality(config_dir)
    loop = _build_agent_loop()

    job: Any
    if job_name == "morning_briefing":
        job = MorningBriefingJob(
            gmail=gmail,
            calendar=calendar,
            agent_loop=loop,
            personality=personality,
            name_for_briefing=name,
        )
    elif job_name == "evening_wrap":
        job = EveningWrapJob(
            gmail=gmail,
            agent_loop=loop,
            personality=personality,
            name_for_briefing=name,
        )
    elif job_name == "pre_meeting_prep":
        job = PreMeetingPrepJob(
            calendar=calendar,
            agent_loop=loop,
            personality=personality,
        )
    elif job_name == "weekly_review":
        job = WeeklyReviewJob(
            gmail=gmail,
            calendar=calendar,
            agent_loop=loop,
            personality=personality,
            name_for_briefing=name,
        )
    elif job_name == "followup_reminder":
        job = FollowupReminderJob(stakeholders=stakeholders)
    else:
        raise click.UsageError(f"Unknown job: {job_name}")

    result = job.run(JobContext(session_id=f"simulate-{job_name}"))
    click.echo(f"=== Simulated {job_name} ===")
    click.echo(result)
