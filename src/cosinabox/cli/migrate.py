"""`cosinabox migrate` — apply schema migrations to user config files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import click
import yaml

from cosinabox.migrations.registry import REGISTRY, current_version

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)

_CONFIG_FILES = (
    "personality.md",
    "stakeholders.yaml",
    "jobs.yaml",
    "integrations.yaml",
)


def _parse_personality(path: Path) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body) for personality.md.

    Raises click.ClickException with the file path on malformed input so
    the CLI surfaces a clean error instead of a traceback.
    """
    if not path.exists():
        raise click.ClickException(f"{path} not found")
    text = path.read_text()
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise click.ClickException(f"{path} missing YAML frontmatter")
    try:
        data: dict[str, Any] = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise click.ClickException(f"{path} has invalid YAML frontmatter: {e}") from e
    body = text[m.end() :]
    return data, body


def _render_personality(frontmatter: dict[str, Any], body: str) -> str:
    """Reassemble a personality.md from its frontmatter dict and body.

    Uses ``yaml.safe_dump`` with ``sort_keys=False`` so key order from the
    migration callable is preserved.
    """
    dumped = yaml.safe_dump(frontmatter, sort_keys=False).rstrip("\n")
    if body.startswith("\n"):
        return f"---\n{dumped}\n---\n{body}"
    return f"---\n{dumped}\n---\n\n{body}"


def _read_yaml_version(path: Path) -> int | None:
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text()) or {}
    raw = data.get("schema_version")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _migrate_personality(config_dir: Path) -> str:
    """Migrate personality.md to the current version. Returns a status line
    for echo. Raises click.ClickException on unrecoverable errors."""
    path = config_dir / "personality.md"
    target = current_version("personality.md")
    frontmatter, body = _parse_personality(path)

    raw = frontmatter.get("schema_version")
    if raw is None:
        raise click.ClickException(f"{path} is missing schema_version in frontmatter")
    try:
        version = int(raw)
    except (TypeError, ValueError) as e:
        raise click.ClickException(f"{path} has non-integer schema_version: {raw!r}") from e

    if version == target:
        return f"personality.md: already at v{target}"
    if version > target:
        raise click.ClickException(
            f"{path} is at schema_version {version}, newer than the engine's "
            f"current v{target}. Upgrade cosinabox before running migrate."
        )

    # Apply migrations in sequence until we reach the target.
    current = frontmatter
    while version < target:
        key = ("personality.md", version)
        migrator = REGISTRY.get(key)
        if migrator is None:
            raise click.ClickException(
                f"{path}: no migration registered from v{version} to "
                f"v{version + 1}. Manual update required."
            )
        current = migrator(current)
        version = int(current.get("schema_version", version + 1))

    path.write_text(_render_personality(current, body))
    return f"personality.md: migrated to v{target}"


@click.command("migrate")
@click.pass_context
def migrate_cmd(ctx: click.Context) -> None:
    """Apply schema migrations to user config files."""
    config_dir: Path = ctx.obj["config_dir"]

    # Personality has a dedicated v1 -> v2 migration; other config files are
    # still at v1 (CURRENT_SCHEMA_VERSION) and only warn on drift.
    click.echo(_migrate_personality(config_dir))

    outdated: list[tuple[str, int]] = []
    for filename in _CONFIG_FILES:
        if filename == "personality.md":
            continue
        version = _read_yaml_version(config_dir / filename)
        if version is None:
            continue
        target = current_version(filename)
        if version < target:
            outdated.append((filename, version))

    if not outdated:
        click.echo("All schemas current.")
        return

    for filename, version in outdated:
        target = current_version(filename)
        key = (filename, version)
        if key in REGISTRY:
            click.echo(f"Migrating {filename} from v{version} to v{version + 1}...")
            # Future: apply migration, write back.
        else:
            click.echo(
                f"WARNING: {filename} is at schema_version {version} "
                f"(current: {target}) but no migration is registered. "
                "Manual update may be required."
            )
