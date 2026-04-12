"""`cosinabox set-persona` — write a persona template to personality.md."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import click

ROLE_CHOICES = click.Choice(["founder"])


@click.command("set-persona")
@click.option("--role", required=True, type=ROLE_CHOICES, help="Persona role template to apply.")
@click.option("--force", is_flag=True, default=False, help="Overwrite existing personality.md.")
@click.pass_context
def set_persona_cmd(ctx: click.Context, role: str, force: bool) -> None:
    """Write a persona template to personality.md in the config directory."""
    config_dir: Path = ctx.obj["config_dir"]
    dest = config_dir / "personality.md"

    if dest.exists() and not force:
        raise click.ClickException("personality.md already exists. Use --force to overwrite.")

    template_text: str = files("cosinabox.personas").joinpath(f"{role}.md").read_text()
    dest.write_text(template_text)
    click.echo(f"Wrote {role} persona template to {dest}.")
