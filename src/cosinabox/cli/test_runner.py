"""`cosinabox test` — wraps pytest with custom_jobs/ on the path."""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path
import click

@click.command("test")
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def test_cmd(ctx: click.Context, pytest_args: tuple[str, ...]) -> None:
    config_dir: Path = ctx.obj["config_dir"]
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{config_dir}{os.pathsep}{env.get('PYTHONPATH', '')}"
    result = subprocess.run([sys.executable, "-m", "pytest", *pytest_args], cwd=config_dir, env=env)
    ctx.exit(result.returncode)
