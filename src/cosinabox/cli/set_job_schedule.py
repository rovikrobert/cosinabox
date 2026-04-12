"""`cosinabox set-job-schedule` — update the cron schedule for a job in jobs.yaml."""

from __future__ import annotations

from pathlib import Path

import click
import yaml
from apscheduler.triggers.cron import CronTrigger


@click.command("set-job-schedule")
@click.argument("job_name")
@click.option("--cron", required=True, help="Cron expression (5 fields).")
@click.pass_context
def set_job_schedule_cmd(ctx: click.Context, job_name: str, cron: str) -> None:
    """Update the cron schedule for a job in jobs.yaml."""
    config_dir: Path = ctx.obj["config_dir"]
    path = config_dir / "jobs.yaml"

    data = yaml.safe_load(path.read_text()) or {}
    jobs = data.get("jobs", {})

    if job_name not in jobs:
        raise click.ClickException(f"Unknown job: {job_name}")

    # Validate cron expression
    try:
        CronTrigger.from_crontab(cron)
    except (ValueError, TypeError) as exc:
        raise click.ClickException(f"Invalid cron expression '{cron}': {exc}") from exc

    jobs[job_name]["schedule"] = cron
    data["jobs"] = jobs
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    click.echo(f"Updated {job_name} schedule to: {cron}")
