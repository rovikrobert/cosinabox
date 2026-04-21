from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli


def test_init_creates_user_repo(tmp_path: Path) -> None:
    target = tmp_path / "my-cos"
    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(target)])
    assert result.exit_code == 0, result.output
    assert (target / "personality.md").exists()
    assert (target / "stakeholders.yaml").exists()
    assert (target / "jobs.yaml").exists()
    assert (target / "integrations.yaml").exists()
    assert (target / "main.py").exists()
    assert (target / "CLAUDE.md").exists()
    assert (target / "docs" / "agent" / "safety.md").exists()
    assert (target / ".cosinabox" / "pre-commit").exists()
    assert "Open this directory in Claude Code" in result.output


def test_init_stamps_engine_version(tmp_path: Path) -> None:
    """`cosinabox init` records the scaffolding engine version in
    ``.cosinabox-version`` so `doctor`/`describe` can surface drift."""
    import cosinabox

    target = tmp_path / "my-cos"
    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(target)])
    assert result.exit_code == 0, result.output
    stamp = target / ".cosinabox-version"
    assert stamp.exists(), "init must write .cosinabox-version"
    assert stamp.read_text().strip() == cosinabox.__version__


def test_init_pyproject_pins_scaffolding_minor(tmp_path: Path) -> None:
    """Scaffolded pyproject pins the cosinabox dep to the scaffolding
    engine's major.minor range (e.g. engine 0.1.x → ``>=0.1,<0.2``)."""
    import re

    import cosinabox

    target = tmp_path / "my-cos"
    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(target)])
    assert result.exit_code == 0, result.output
    pyproject_text = (target / "pyproject.toml").read_text()

    m = re.match(r"(\d+)\.(\d+)", cosinabox.__version__)
    assert m is not None, f"engine version {cosinabox.__version__} not semver-ish"
    major, minor = int(m.group(1)), int(m.group(2))
    expected_pin = f"cosinabox[google]>={major}.{minor},<{major}.{minor + 1}"

    assert expected_pin in pyproject_text, (
        f"scaffolded pyproject must pin to the scaffolding engine's minor series "
        f"({expected_pin!r}). Got:\n{pyproject_text}"
    )


def test_init_refuses_non_empty_dir(tmp_path: Path) -> None:
    target = tmp_path / "my-cos"
    target.mkdir()
    (target / "junk.txt").write_text("hi")
    runner = CliRunner()
    result = runner.invoke(cli, ["init", str(target)])
    assert result.exit_code != 0
    assert "not empty" in result.output.lower()
