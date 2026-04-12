"""Doctor check definitions."""

from __future__ import annotations

import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from cosinabox import defaults


@dataclass
class CheckResult:
    name: str
    status: str  # "pass" | "fail" | "warn"
    message: str


class Check(ABC):
    name: str
    severity: str = "warn"

    @abstractmethod
    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult: ...


class PersonalityThinCheck(Check):
    name = "personality_thin"
    severity = "warn"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:
        path = config_dir / "personality.md"
        if not path.exists():
            return CheckResult(self.name, "fail", "personality.md missing")
        text = path.read_text()
        if len(text) < defaults.DOCTOR_PERSONALITY_MIN_CHARS:
            return CheckResult(
                self.name,
                "fail",
                f"personality.md is {len(text)} chars; "
                f"under {defaults.DOCTOR_PERSONALITY_MIN_CHARS} threshold. "
                f"Generic personality = generic briefings.",
            )
        return CheckResult(self.name, "pass", "personality is substantive")


class StakeholdersEmptyCheck(Check):
    name = "stakeholders_empty"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:
        path = config_dir / "stakeholders.yaml"
        if not path.exists():
            return CheckResult(self.name, "fail", "stakeholders.yaml missing")
        data = yaml.safe_load(path.read_text()) or {}
        count = len(data.get("stakeholders", []))
        installed = history.get("installed_date")
        if installed is None:
            return CheckResult(self.name, "warn", "no install date in history")
        days = (date.today() - date.fromisoformat(installed)).days
        if (
            days >= defaults.DOCTOR_STAKEHOLDERS_MIN_AFTER_DAYS
            and count < defaults.DOCTOR_STAKEHOLDERS_MIN_COUNT
        ):
            return CheckResult(
                self.name,
                "fail",
                f"only {count} stakeholders after {days} days; followup_reminder won't have data",
            )
        return CheckResult(self.name, "pass", f"{count} stakeholders")


class CostRunawayCheck(Check):
    name = "cost_runaway"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:
        spend = history.get("daily_spend") or {}
        if not spend:
            return CheckResult(self.name, "warn", "no spend data yet")
        cap = defaults.COST_DAILY_CAP_USD
        threshold = cap * defaults.DOCTOR_COST_RUNAWAY_RATIO
        hot_days = [d for d, s in spend.items() if s > threshold]
        if hot_days:
            return CheckResult(
                self.name,
                "fail",
                f"{len(hot_days)} day(s) above "
                f"{defaults.DOCTOR_COST_RUNAWAY_RATIO * 100:.0f}% "
                f"of cap (${cap:.0f}/day)",
            )
        return CheckResult(self.name, "pass", "spend within cap")


class ToolLoopExcessCheck(Check):
    name = "tool_loop_excess"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:
        avg = history.get("avg_tool_iterations_per_message")
        if avg is None:
            return CheckResult(self.name, "warn", "no iteration data yet")
        if avg > defaults.DOCTOR_TOOL_LOOP_AVG_THRESHOLD:
            return CheckResult(
                self.name,
                "fail",
                f"avg {avg:.1f} tool iterations per message; prompts may be too vague",
            )
        return CheckResult(self.name, "pass", f"avg {avg:.1f} iterations")


class PrepNoiseCheck(Check):
    name = "prep_noise"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:
        fires = history.get("prep_fires_per_day")
        if fires is None:
            return CheckResult(self.name, "warn", "no fire-rate data")
        if fires > defaults.DOCTOR_PREP_NOISE_PER_DAY:
            return CheckResult(
                self.name, "fail", f"pre_meeting_prep firing {fires}x per day; tune skip filters"
            )
        return CheckResult(self.name, "pass", f"{fires}/day")


class BriefingDriftCheck(Check):
    name = "briefing_drift"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:
        override = config_dir / "prompts" / "morning_briefing.md"
        if not override.exists():
            return CheckResult(self.name, "pass", "no override")
        sim_log = history.get("simulate_log") or []
        if "morning_briefing" not in sim_log:
            return CheckResult(
                self.name,
                "fail",
                "morning_briefing overridden but never simulated; "
                "run `cosinabox simulate morning_briefing`",
            )
        return CheckResult(self.name, "pass", "override validated by simulate")


_SECRET_PATTERNS = re.compile(
    r"(sk-ant-[A-Za-z0-9_-]+|xoxb-[A-Za-z0-9-]+|AIza[0-9A-Za-z_-]{35}|ghp_[A-Za-z0-9]{36})"
)


class SecretInTrackedFileCheck(Check):
    name = "secret_in_tracked_file"
    severity = "critical"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:
        try:
            ls = subprocess.run(
                ["git", "ls-files"], cwd=config_dir, capture_output=True, text=True, check=True
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return CheckResult(self.name, "warn", "not a git repo")
        leaks: list[str] = []
        for relpath in ls.stdout.splitlines():
            full = config_dir / relpath
            try:
                text = full.read_text()
            except (UnicodeDecodeError, FileNotFoundError):
                continue
            if _SECRET_PATTERNS.search(text):
                leaks.append(relpath)
        if leaks:
            return CheckResult(
                self.name, "fail", f"possible secrets in: {', '.join(leaks)} — rotate immediately"
            )
        return CheckResult(self.name, "pass", "no secret patterns found")


class StaleFollowupsCheck(Check):
    name = "stale_followups"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:
        path = config_dir / "stakeholders.yaml"
        if not path.exists():
            return CheckResult(self.name, "warn", "no stakeholders.yaml")
        data = yaml.safe_load(path.read_text()) or {}
        cadence_days = {"daily": 1, "weekly": 7, "biweekly": 14, "monthly": 30, "quarterly": 90}
        stale = 0
        for s in data.get("stakeholders", []):
            lc = s.get("last_contact")
            if not lc:
                continue
            days = (date.today() - date.fromisoformat(lc)).days
            cd = cadence_days.get(s.get("cadence", "weekly"), 7)
            if days > cd + defaults.FOLLOWUP_STALENESS_DAYS:
                stale += 1
        if stale > defaults.DOCTOR_STALE_FOLLOWUP_COUNT:
            return CheckResult(
                self.name,
                "fail",
                f"{stale} stakeholders past their cadence; user may not be acting on briefings",
            )
        return CheckResult(self.name, "pass", f"{stale} stale")


class OAuthExpiringCheck(Check):
    name = "oauth_expiring"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:
        expires = history.get("google_token_expires")
        if expires is None:
            return CheckResult(self.name, "warn", "no token expiry data")
        days_until = (date.fromisoformat(expires) - date.today()).days
        if days_until < defaults.DOCTOR_OAUTH_EXPIRY_WARN_DAYS:
            return CheckResult(
                self.name,
                "fail",
                f"OAuth token expires in {days_until} days; re-run `cosinabox auth google`",
            )
        return CheckResult(self.name, "pass", f"{days_until} days")


class SchemaOutdatedCheck(Check):
    name = "schema_outdated"

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:
        from cosinabox.migrations.registry import CURRENT_SCHEMA_VERSION

        outdated: list[str] = []
        for fname in ("stakeholders.yaml", "jobs.yaml", "integrations.yaml"):
            path = config_dir / fname
            if not path.exists():
                continue
            data = yaml.safe_load(path.read_text()) or {}
            v = data.get("schema_version")
            if v is not None and v < CURRENT_SCHEMA_VERSION:
                outdated.append(f"{fname} (v{v})")
        if outdated:
            return CheckResult(
                self.name, "fail", f"outdated: {', '.join(outdated)} — run `cosinabox migrate`"
            )
        return CheckResult(self.name, "pass", "schemas current")
