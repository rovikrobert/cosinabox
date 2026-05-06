"""`cosinabox doctor`."""

from __future__ import annotations

import json as jsonlib
from pathlib import Path
from typing import Any

import click

from cosinabox.doctor.registry import REGISTRY


def _load_history(config_dir: Path) -> dict[str, Any]:
    path = config_dir / ".cosinabox" / "history.json"
    if path.exists():
        try:
            data = jsonlib.loads(path.read_text())
            return data if isinstance(data, dict) else {}
        except jsonlib.JSONDecodeError:
            return {}
    return {}


@click.command("doctor")
@click.option("--json", "json_out", is_flag=True)
@click.option(
    "--offline",
    is_flag=True,
    default=False,
    help="Skip checks that require network access (e.g. live OAuth probe).",
)
@click.pass_context
def doctor_cmd(ctx: click.Context, json_out: bool, offline: bool) -> None:
    """Run all health checks."""
    config_dir: Path = ctx.obj["config_dir"]
    history = _load_history(config_dir)
    checks = [c for c in REGISTRY if not (offline and c.network)]
    results = [c.run(config_dir=config_dir, history=history) for c in checks]
    if json_out:
        click.echo(
            jsonlib.dumps(
                [{"name": r.name, "status": r.status, "message": r.message} for r in results],
                indent=2,
            )
        )
    else:
        for r in results:
            icon = {"pass": "OK", "warn": "WARN", "fail": "FAIL"}.get(r.status, "?")
            click.echo(f"[{icon}] {r.name}: {r.message}")
    if any(r.status == "fail" for r in results):
        ctx.exit(1)
