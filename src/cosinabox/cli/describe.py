"""`cosinabox describe` — print a human-readable summary of the user repo."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import click
import yaml

from cosinabox.stakeholders import get_stakeholders


def _parse_personality(path: Path) -> dict[str, Any]:
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    frontmatter: dict[str, Any] = yaml.safe_load(m.group(1)) if m else {}
    return frontmatter


def _load_yaml(path: Path) -> dict[str, Any]:
    if path.exists():
        result: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
        return result
    return {}


def _build_data(config_dir: Path) -> dict[str, Any]:
    personality = _parse_personality(config_dir / "personality.md")
    jobs_doc = _load_yaml(config_dir / "jobs.yaml")
    integrations_doc = _load_yaml(config_dir / "integrations.yaml")
    integrations = integrations_doc.get("integrations", {})

    stakeholders = get_stakeholders(config_dir=config_dir, integrations=integrations)
    jobs = jobs_doc.get("jobs", {})

    enabled_jobs = {k: v for k, v in jobs.items() if v.get("enabled")}
    enabled_integrations = [k for k, v in integrations.items() if v.get("enabled")]

    return {
        "name": personality.get("name", "Unknown"),
        "role": personality.get("role", "Unknown"),
        "timezone": personality.get("timezone", "Unknown"),
        "stakeholders": [
            {
                "name": s.get("name"),
                "role": s.get("role"),
                "cadence": s.get("cadence"),
                "last_contact": s.get("last_contact"),
            }
            for s in stakeholders
        ],
        "jobs": {
            name: {
                "schedule": cfg.get("schedule"),
                "minutes_before": cfg.get("minutes_before"),
            }
            for name, cfg in enabled_jobs.items()
        },
        "integrations": enabled_integrations,
    }


def _format_english(data: dict[str, Any]) -> str:
    lines = []
    lines.append(f"Name:      {data['name']}")
    lines.append(f"Role:      {data['role']}")
    lines.append(f"Timezone:  {data['timezone']}")
    lines.append("")

    stakeholders = data.get("stakeholders", [])
    if stakeholders:
        lines.append(f"Stakeholders ({len(stakeholders)}):")
        for s in stakeholders:
            cadence = s.get("cadence", "unknown cadence")
            role = s.get("role", "")
            last = s.get("last_contact", "")
            detail = f"  - {s['name']}"
            if role:
                detail += f" ({role})"
            detail += f" — {cadence}"
            if last:
                detail += f", last contact {last}"
            lines.append(detail)
    else:
        lines.append("Stakeholders: none")

    lines.append("")
    jobs = data.get("jobs", {})
    if jobs:
        lines.append(f"Enabled jobs ({len(jobs)}):")
        for job_name, cfg in jobs.items():
            sched = cfg.get("schedule")
            mins = cfg.get("minutes_before")
            if sched:
                lines.append(f"  - {job_name}: {sched}")
            elif mins:
                lines.append(f"  - {job_name}: {mins} minutes before events")
            else:
                lines.append(f"  - {job_name}")
    else:
        lines.append("Enabled jobs: none")

    lines.append("")
    integrations = data.get("integrations", [])
    if integrations:
        lines.append("Enabled integrations: " + ", ".join(integrations))
    else:
        lines.append("Enabled integrations: none")

    return "\n".join(lines)


@click.command("describe")
@click.option(
    "--json", "as_json", is_flag=True, default=False, help="Output JSON instead of prose."
)
@click.pass_context
def describe_cmd(ctx: click.Context, as_json: bool) -> None:
    """Print a summary of the current user repo configuration."""
    config_dir: Path = ctx.obj["config_dir"]
    data = _build_data(config_dir)
    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        click.echo(_format_english(data))
