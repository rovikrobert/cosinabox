"""`cosinabox validate` — schema-check all user config files."""

from __future__ import annotations

import json
import re
from pathlib import Path

import click
import yaml
from jsonschema import ValidationError, validate

from cosinabox.schemas import load_schema

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def _load_personality_frontmatter(path: Path) -> dict:
    text = path.read_text()
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("personality.md missing YAML frontmatter")
    return yaml.safe_load(m.group(1))


def _validate_one(
    config_dir: Path, filename: str, schema_name: str, loader
) -> tuple[bool, str]:
    path = config_dir / filename
    if not path.exists():
        return False, f"{filename} MISSING"
    try:
        instance = loader(path)
        validate(instance=instance, schema=load_schema(schema_name))
        return True, f"{filename} PASS"
    except ValidationError as e:
        return False, f"{filename} FAIL: {e.message}"
    except Exception as e:
        return False, f"{filename} FAIL: {e}"


@click.command("validate")
@click.option("--json", "json_out", is_flag=True, help="Output results as JSON.")
@click.pass_context
def validate_cmd(ctx: click.Context, json_out: bool) -> None:
    """Schema-check all user config files."""
    config_dir: Path = ctx.obj["config_dir"]
    targets = [
        ("personality.md", "personality", _load_personality_frontmatter),
        ("stakeholders.yaml", "stakeholders", lambda p: yaml.safe_load(p.read_text())),
        ("jobs.yaml", "jobs", lambda p: yaml.safe_load(p.read_text())),
        ("integrations.yaml", "integrations", lambda p: yaml.safe_load(p.read_text())),
    ]
    results = [_validate_one(config_dir, *t) for t in targets]
    if json_out:
        click.echo(
            json.dumps(
                [{"file": r[1].split()[0], "ok": r[0], "msg": r[1]} for r in results],
                indent=2,
            )
        )
    else:
        for ok, msg in results:
            click.echo(msg)
    if not all(ok for ok, _ in results):
        ctx.exit(1)
