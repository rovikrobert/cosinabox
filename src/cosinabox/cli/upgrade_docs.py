"""`cosinabox upgrade-docs` — re-sync docs and config files from engine template."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import click

TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates" / "user-repo"

REFRESH_PATHS = (
    "docs/agent/safety.md",
    "docs/agent/persona-interview.md",
    "docs/agent/editing-config.md",
    "docs/agent/adding-custom-jobs.md",
    "docs/agent/oauth-walkthrough.md",
    "docs/agent/proactive-suggestions.md",
    "BEST_PRACTICES.md",
    "CLAUDE.md",
    ".cosinabox/pre-commit",
    ".cosinabox/install-hook.sh",
    ".cosinabox/README.md",
)


@click.command("upgrade-docs")
@click.pass_context
def upgrade_docs_cmd(ctx: click.Context) -> None:
    """Re-sync docs and .cosinabox/ files from engine template."""
    config_dir: Path = ctx.obj["config_dir"]

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = config_dir / ".cosinabox" / f"backup-{timestamp}"
    backed_up: list[str] = []

    for rel in REFRESH_PATHS:
        src = TEMPLATE_ROOT / rel
        dst = config_dir / rel

        if not src.exists():
            click.echo(f"SKIP {rel} (not in template)")
            continue

        src_text = src.read_text()

        if dst.exists():
            dst_text = dst.read_text()
            if dst_text == src_text:
                click.echo(f"  OK {rel} (already current)")
                continue
            # Back up modified file
            backup_path = backup_dir / rel
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, backup_path)
            backed_up.append(rel)

        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src_text)
        click.echo(f"  UPDATED {rel}")

    if backed_up:
        click.echo(f"\nBackup saved to: .cosinabox/backup-{timestamp}/")
        for f in backed_up:
            click.echo(f"  {f}")
    else:
        click.echo("\nAll files already current or no backups needed.")
