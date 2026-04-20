"""`cosinabox describe` — print a human-readable summary of the user repo."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import click
import yaml


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


def _commitment_counts(config_dir: Path) -> dict[str, int] | None:
    """Peek at the commitments table if a memory.db exists. Returns None
    if the DB isn't there (fresh repo, haven't started the app yet) or
    can't be read — we stay silent rather than crash ``describe``.
    """
    import sqlite3

    db_path = config_dir / ".cosinabox" / "memory.db"
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT status, COUNT(*) AS n FROM commitments GROUP BY status")
        counts = {row["status"]: int(row["n"]) for row in cur.fetchall()}
        conn.close()
        return counts
    except sqlite3.Error:
        return None


def _build_data(config_dir: Path) -> dict[str, Any]:
    from cosinabox.stakeholders import get_stakeholders

    personality = _parse_personality(config_dir / "personality.md")
    jobs_doc = _load_yaml(config_dir / "jobs.yaml")
    integrations_doc = _load_yaml(config_dir / "integrations.yaml")

    jobs = jobs_doc.get("jobs", {})
    integrations = integrations_doc.get("integrations", {})

    stakeholders = get_stakeholders(config_dir=config_dir, integrations=integrations)

    enabled_jobs = {k: v for k, v in jobs.items() if v.get("enabled")}
    enabled_integrations = [k for k, v in integrations.items() if v.get("enabled")]
    disabled_integrations = [k for k, v in integrations.items() if not v.get("enabled")]

    import os

    memory_backend = "remote" if os.getenv("MEMORY_SERVICE_URL") else "local"

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
            for s in (stakeholders or [])
        ],
        "jobs": {
            name: {
                "schedule": cfg.get("schedule"),
                "minutes_before": cfg.get("minutes_before"),
            }
            for name, cfg in enabled_jobs.items()
        },
        "integrations": enabled_integrations,
        "disabled_integrations": disabled_integrations,
        "memory_backend": memory_backend,
        "commitments": _commitment_counts(config_dir),
    }


def _format_english(data: dict[str, Any]) -> str:
    lines = []
    lines.append(f"Name:      {data['name']}")
    lines.append(f"Role:      {data['role']}")
    lines.append(f"Timezone:  {data['timezone']}")
    lines.append(f"Memory: {data.get('memory_backend', 'local')}")
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

    disabled = data.get("disabled_integrations", [])
    if disabled:
        fallbacks = {
            "google": "no email/calendar in briefings or DM",
            "attio": "using stakeholders.yaml instead of CRM",
            "fireflies": "no meeting transcript access",
            "web_search": "no web search in DM",
        }
        parts = [f"{k} ({fallbacks.get(k, 'disabled')})" for k in disabled]
        lines.append("Disabled integrations: " + ", ".join(parts))

    counts = data.get("commitments")
    if counts:
        lines.append("")
        open_n = counts.get("open", 0) + counts.get("in_progress", 0) + counts.get("blocked", 0)
        done_n = counts.get("done", 0)
        cancelled_n = counts.get("cancelled", 0)
        lines.append(f"Commitments: {open_n} open, {done_n} done, {cancelled_n} cancelled")

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
