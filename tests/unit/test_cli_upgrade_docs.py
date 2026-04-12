from __future__ import annotations

import shutil
from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "src" / "cosinabox" / "templates" / "user-repo"


def test_upgrade_docs_refreshes_subdocs(tmp_path: Path) -> None:
    shutil.copytree(TEMPLATE, tmp_path / "cos")
    user = tmp_path / "cos"
    safety = user / "docs" / "agent" / "safety.md"
    safety.write_text("STALE STALE STALE")
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(user), "upgrade-docs"])
    assert result.exit_code == 0
    assert "STALE STALE STALE" not in safety.read_text()
    backups = list((user / ".cosinabox").glob("backup-*"))
    assert len(backups) == 1
