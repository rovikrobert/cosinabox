"""`cosinabox init <dir>` — scaffold a new user repo."""

from __future__ import annotations

import shutil
from pathlib import Path

import click

TEMPLATE_ROOT = (
    Path(__file__).resolve().parents[1] / "templates" / "user-repo"
)


@click.command("init")
@click.argument("dest", type=click.Path(file_okay=False, path_type=Path))
def init_cmd(dest: Path) -> None:
    """Scaffold a new user repo at <dest>."""
    if dest.exists() and any(dest.iterdir()):
        raise click.ClickException(f"{dest} exists and is not empty.")
    shutil.copytree(TEMPLATE_ROOT, dest)
    # Make hook executable (copytree drops permissions on some systems).
    hook = dest / ".cosinabox" / "pre-commit"
    if hook.exists():
        hook.chmod(0o755)
    install = dest / ".cosinabox" / "install-hook.sh"
    if install.exists():
        install.chmod(0o755)
    click.echo(f"Your CoSinaBox skeleton is ready in {dest}.")
    click.echo("Open this directory in Claude Code (or Cursor) and say 'set up my CoS.'")
    click.echo("Claude Code will read CLAUDE.md and walk you through the rest.")
