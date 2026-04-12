"""`cosinabox disable-job` — set enabled=False for a job in jobs.yaml."""

from __future__ import annotations

from pathlib import Path

import click

from cosinabox.cli.enable_job import _flip


@click.command("disable-job")
@click.argument("job_name")
@click.pass_context
def disable_job_cmd(ctx: click.Context, job_name: str) -> None:
    """Disable a job in jobs.yaml."""
    config_dir: Path = ctx.obj["config_dir"]
    _flip(config_dir, job_name, False)
    click.echo(f"Disabled job: {job_name}")
