"""`cosinabox init <dir>` — scaffold a new user repo."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import click

import cosinabox

TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates" / "user-repo"

# Matches the cosinabox dep line in the template pyproject so we can
# rewrite it to the scaffolding engine's major.minor range. Captures the
# extras group so callers can extend it (e.g. `[google,fireflies]`).
_COSINABOX_PIN_RE = re.compile(r'"cosinabox(\[[^\]]*\])?>=\d+\.\d+,<\d+\.\d+"')


def _engine_pin(extras: str) -> str:
    """Return a pin string like ``"cosinabox[google]>=0.1,<0.2"`` for the
    current engine ``cosinabox.__version__``."""
    m = re.match(r"(\d+)\.(\d+)", cosinabox.__version__)
    if m is None:
        # Fallback: leave the template pin untouched if the version string
        # is non-semver (shouldn't happen for shipped releases).
        raise click.ClickException(
            f"cannot parse cosinabox.__version__ ({cosinabox.__version__!r}) as major.minor"
        )
    major, minor = int(m.group(1)), int(m.group(2))
    return f'"cosinabox{extras}>={major}.{minor},<{major}.{minor + 1}"'


def _stamp_pyproject(pyproject: Path) -> None:
    """Rewrite the cosinabox dep pin to match the scaffolding engine."""
    if not pyproject.exists():
        return
    text = pyproject.read_text()

    def _sub(match: re.Match[str]) -> str:
        return _engine_pin(match.group(1) or "")

    new_text, n = _COSINABOX_PIN_RE.subn(_sub, text)
    if n:
        pyproject.write_text(new_text)


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

    # Record the scaffolding engine version so `doctor`/`describe` can
    # surface drift between what was scaffolded and what's installed.
    (dest / ".cosinabox-version").write_text(cosinabox.__version__ + "\n")

    # Pin the user's pyproject to the scaffolding engine's minor series.
    # Template ships a placeholder pin; rewrite it to match engine
    # __version__ so the generated repo installs reliably.
    _stamp_pyproject(dest / "pyproject.toml")

    click.echo(f"Your CoSinaBox skeleton is ready in {dest}.")
    click.echo("Open this directory in Claude Code (or Cursor) and say 'set up my CoS.'")
    click.echo("Claude Code will read CLAUDE.md and walk you through the rest.")
