from __future__ import annotations
from pathlib import Path
from click.testing import CliRunner
from cosinabox.cli.main import cli

def test_interview_start_then_answer(tmp_path: Path) -> None:
    runner = CliRunner()
    r1 = runner.invoke(cli, ["-C", str(tmp_path), "interview", "--start"])
    assert r1.exit_code == 0
    assert "Step 1/10" in r1.output
    r2 = runner.invoke(cli, ["-C", str(tmp_path), "interview", "--answer",
         "Alex, Founder, Loop, UTC"])
    assert r2.exit_code == 0
    assert "Step 2/10" in r2.output or "Stakes" in r2.output
    assert (tmp_path / "personality.md").exists()
