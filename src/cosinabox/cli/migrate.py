"""`cosinabox migrate` — apply schema migrations to user config files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import click
import yaml

from cosinabox.migrations.registry import CURRENT_SCHEMA_VERSION, REGISTRY

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)

_CONFIG_FILES = (
    "personality.md",
    "stakeholders.yaml",
    "jobs.yaml",
    "integrations.yaml",
)


def _read_version(config_dir: Path, filename: str) -> int | None:
    path = config_dir / filename
    if not path.exists():
        return None
    text = path.read_text()
    if filename.endswith(".md"):
        m = _FRONTMATTER_RE.match(text)
        if not m:
            return None
        data: dict[str, Any] = yaml.safe_load(m.group(1))
    else:
        data = yaml.safe_load(text)
    return int(data.get("schema_version", 0))


@click.command("migrate")
@click.pass_context
def migrate_cmd(ctx: click.Context) -> None:
    """Apply schema migrations to user config files."""
    config_dir: Path = ctx.obj["config_dir"]

    outdated: list[tuple[str, int]] = []
    for filename in _CONFIG_FILES:
        version = _read_version(config_dir, filename)
        if version is None:
            click.echo(f"{filename}: not found, skipping")
            continue
        if version < CURRENT_SCHEMA_VERSION:
            outdated.append((filename, version))

    if not outdated:
        click.echo("All schemas current.")
        return

    for filename, version in outdated:
        key = (filename, version)
        if key in REGISTRY:
            click.echo(f"Migrating {filename} from v{version} to v{version + 1}...")
            # Future: apply migration, write back
        else:
            click.echo(
                f"WARNING: {filename} is at schema_version {version} "
                f"(current: {CURRENT_SCHEMA_VERSION}) but no migration is registered. "
                "Manual update may be required."
            )
