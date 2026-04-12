"""cosinabox CLI entry point."""

from __future__ import annotations

import os
from pathlib import Path

import click

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


cli.add_command(validate_cmd)


if __name__ == "__main__":
    cli()
