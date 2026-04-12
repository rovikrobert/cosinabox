"""cosinabox CLI entry point."""

from __future__ import annotations

import os
from pathlib import Path

import click

from cosinabox.cli.add_stakeholder import add_stakeholder_cmd
from cosinabox.cli.describe import describe_cmd
from cosinabox.cli.disable_job import disable_job_cmd
from cosinabox.cli.enable_job import enable_job_cmd
from cosinabox.cli.init import init_cmd
from cosinabox.cli.set_job_schedule import set_job_schedule_cmd
from cosinabox.cli.simulate import simulate_cmd
from cosinabox.cli.validate import validate_cmd


@click.group()
@click.option(
    "-C",
    "--config-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=lambda: Path(os.getenv("COSINABOX_CONFIG_DIR", os.getcwd())),
    help="User repo config directory.",
)
@click.version_option()
@click.pass_context
def cli(ctx: click.Context, config_dir: Path) -> None:
    """CoSinaBox — open-source Chief of Staff."""
    ctx.ensure_object(dict)
    ctx.obj["config_dir"] = config_dir


cli.add_command(init_cmd)
cli.add_command(validate_cmd)
cli.add_command(simulate_cmd)
cli.add_command(describe_cmd)
cli.add_command(add_stakeholder_cmd)
cli.add_command(set_job_schedule_cmd)
cli.add_command(enable_job_cmd)
cli.add_command(disable_job_cmd)


if __name__ == "__main__":
    cli()
