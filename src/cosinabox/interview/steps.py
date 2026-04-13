"""Interview step definitions."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

import yaml


class Step(ABC):
    name: str

    @abstractmethod
    def prompt(self) -> str: ...
    @abstractmethod
    def apply(self, answer: str, config_dir: Path) -> None: ...


class IdentityStep(Step):
    name = "identity"

    def prompt(self) -> str:
        return (
            "Step 1/10 — Identity. Tell me your name, role, company, and timezone "
            "(comma-separated, e.g. 'Alex, Founder, Loop AI, America/Los_Angeles')."
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        from cosinabox.timezone import resolve_timezone

        parts = [p.strip() for p in answer.split(",", 3)]
        while len(parts) < 4:
            parts.append("")
        name, role, company, tz_raw = parts
        tz = resolve_timezone(tz_raw) or tz_raw
        text = (
            f"---\nschema_version: 1\nname: {name}\n"
            f"role: {role} at {company}\ntimezone: {tz}\n---\n\n"
            f"# Voice\n(filled in by step 3)\n\n"
            f"# Stakes\n(filled in by step 2)\n\n"
            f"# Defaults\n- Default to bullets, not paragraphs\n"
        )
        (config_dir / "personality.md").write_text(text)


class StakesStep(Step):
    name = "stakes"

    def prompt(self) -> str:
        return (
            "Step 2/10 — Stakes. What's the most important thing happening in your work over "
            "the next 6 weeks? A CoS without stakes is a chatbot."
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        path = config_dir / "personality.md"
        text = path.read_text()
        text = re.sub(
            r"# Stakes\n.*?(\n#|\Z)", f"# Stakes\n{answer}\n\\1", text, count=1, flags=re.DOTALL
        )
        path.write_text(text)


class VoiceStep(Step):
    name = "voice"

    def prompt(self) -> str:
        return (
            "Step 3/10 — Voice. Pick one: blunt / warm / analytical / formal / playful. "
            "Pick a runner-up if you want."
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        path = config_dir / "personality.md"
        text = path.read_text()
        text = re.sub(
            r"# Voice\n.*?(\n#)",
            f"# Voice\nYou are my Chief of Staff. Be {answer.strip()}.\n\\1",
            text,
            count=1,
            flags=re.DOTALL,
        )
        path.write_text(text)


class StakeholdersStep(Step):
    name = "stakeholders"

    def prompt(self) -> str:
        return (
            "Step 4/10 — Top stakeholders. Name your 5 most important people right now. "
            "For each, give name, role, cadence (daily/weekly/biweekly/monthly), and one note. "
            "Format: 'Name, Role, cadence, note' — one per line, or just one to start."
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        path = config_dir / "stakeholders.yaml"
        existing = (
            yaml.safe_load(path.read_text())
            if path.exists()
            else {"schema_version": 1, "stakeholders": []}
        )
        for line in answer.splitlines():
            parts = [p.strip() for p in line.split(",", 3)]
            if len(parts) < 3:
                continue
            name, role, cadence = parts[:3]
            note = parts[3] if len(parts) > 3 else ""
            existing["stakeholders"].append(
                {
                    "name": name,
                    "role": role,
                    "cadence": cadence,
                    "last_contact": "2026-01-01",
                    "notes": note,
                }
            )
        path.write_text(yaml.safe_dump(existing, sort_keys=False))


class CalendarRealityStep(Step):
    name = "calendar_reality"

    def prompt(self) -> str:
        return (
            "Step 5/10 — Calendar reality. What should pre-meeting prep skip? "
            "Common: 'lunch', 'focus block', '1:1'. Comma-separated, or 'none'."
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        path = config_dir / "jobs.yaml"
        data = (
            yaml.safe_load(path.read_text()) if path.exists() else {"schema_version": 1, "jobs": {}}
        )
        skips = (
            []
            if answer.strip().lower() == "none"
            else [s.strip() for s in answer.split(",") if s.strip()]
        )
        data["jobs"].setdefault("pre_meeting_prep", {"enabled": True})
        data["jobs"]["pre_meeting_prep"]["skip_if_calendar_title_matches"] = skips
        path.write_text(yaml.safe_dump(data, sort_keys=False))


class JobStagingStep(Step):
    name = "job_staging"

    def prompt(self) -> str:
        return (
            "Step 6/10 — Job staging. For week 1, I'm enabling only morning_briefing "
            "and pre_meeting_prep. Sound good? (yes/no)"
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        path = config_dir / "jobs.yaml"
        data = (
            yaml.safe_load(path.read_text()) if path.exists() else {"schema_version": 1, "jobs": {}}
        )
        for j in ("morning_briefing", "pre_meeting_prep"):
            data["jobs"].setdefault(j, {})
            data["jobs"][j]["enabled"] = True
        for j in ("evening_wrap", "weekly_review", "followup_reminder"):
            data["jobs"].setdefault(j, {})
            data["jobs"][j]["enabled"] = False
        data["jobs"]["morning_briefing"].setdefault("schedule", "0 8 * * *")
        path.write_text(yaml.safe_dump(data, sort_keys=False))


class OAuthStep(Step):
    name = "oauth"

    def prompt(self) -> str:
        return (
            "Step 7/10 — API keys + OAuth. Walk through docs/agent/oauth-walkthrough.md "
            "with me. When you've finished and have GOOGLE_OAUTH_REFRESH_TOKEN in .env, say 'done'."
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        pass  # No file writes — user did work in .env


class BudgetStep(Step):
    name = "budget"

    def prompt(self) -> str:
        return (
            "Step 8/10 — Budget caps. Default daily cap is $15. Want to change? "
            "(say 'yes default cap' or give a number like '$25')"
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        pass  # v0.1 stores cap in .env


class FirstSimulationStep(Step):
    name = "first_simulation"

    def prompt(self) -> str:
        return (
            "Step 9/10 — First simulation. I'm about to run "
            "`cosinabox simulate morning_briefing --fixture=sample` and show you the output. Ready?"
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        pass  # Agent runs simulate externally


class DeployStep(Step):
    name = "deploy"

    def prompt(self) -> str:
        return (
            "Step 10/10 — Deploy. I'll walk you through the Railway template + GitHub "
            "repo connect + env var entry. Ready? (yes/no)"
        )

    def apply(self, answer: str, config_dir: Path) -> None:
        pass  # Deployment is external


STEPS: list[Step] = [
    IdentityStep(),
    StakesStep(),
    VoiceStep(),
    StakeholdersStep(),
    CalendarRealityStep(),
    JobStagingStep(),
    OAuthStep(),
    BudgetStep(),
    FirstSimulationStep(),
    DeployStep(),
]
