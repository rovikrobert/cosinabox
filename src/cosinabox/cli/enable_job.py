"""`cosinabox enable-job` — set enabled=True for a job in jobs.yaml."""

from __future__ import annotations

from pathlib import Path

import click
import yaml


def _flip(config_dir: Path, job_name: str, value: bool) -> None:
    path = config_dir / "jobs.yaml"
    data = yaml.safe_load(path.read_text())
    if job_name not in data.get("jobs", {}):
        raise click.ClickException(f"Unknown job: {job_name}")
    data["jobs"][job_name]["enabled"] = value
    path.write_text(yaml.safe_dump(data, sort_keys=False))


@click.command("enable-job")
@click.argument("job_name")
@click.pass_context
def enable_job_cmd(ctx: click.Context, job_name: str) -> None:
    """Enable a job in jobs.yaml."""
    config_dir: Path = ctx.obj["config_dir"]
    _flip(config_dir, job_name, True)
    click.echo(f"Enabled job: {job_name}")
