"""Tests for the personality.md v1 -> v2 migration."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cosinabox.cli.main import cli


def test_migrate_v1_personality_rewrites_to_v2(tmp_path: Path) -> None:
    """A v1 personality.md with nothing else becomes v2. Body content and
    other frontmatter keys are untouched — only schema_version changes."""
    body = (
        "---\n"
        "schema_version: 1\n"
        "name: Ada\n"
        "role: Founder\n"
        "timezone: UTC\n"
        "---\n"
        "\n"
        "# Voice\n"
        "be brief\n"
        "\n"
        "# Stakes\n"
        "launching next week\n"
    )
    (tmp_path / "personality.md").write_text(body)

    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "migrate"])
    assert result.exit_code == 0, result.output

    after = (tmp_path / "personality.md").read_text()
    assert "schema_version: 2" in after
    assert "schema_version: 1" not in after
    # Everything else preserved verbatim.
    assert "name: Ada" in after
    assert "role: Founder" in after
    assert "timezone: UTC" in after
    assert "# Voice\nbe brief" in after
    assert "# Stakes\nlaunching next week" in after


def test_migrate_v2_personality_is_noop(tmp_path: Path) -> None:
    """Running migrate on an already-v2 file doesn't rewrite it."""
    body = "---\nschema_version: 2\nname: Ada\ntimezone: UTC\n---\n\n# Voice\nbe brief\n"
    (tmp_path / "personality.md").write_text(body)
    before_mtime = (tmp_path / "personality.md").stat().st_mtime_ns

    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "migrate"])
    assert result.exit_code == 0, result.output

    after = (tmp_path / "personality.md").read_text()
    assert after == body
    # File should not have been rewritten.
    assert (tmp_path / "personality.md").stat().st_mtime_ns == before_mtime


def test_migrate_invalid_schema_version_errors(tmp_path: Path) -> None:
    """An unknown/invalid schema_version (not 1 and not current) errors clearly
    with the file path mentioned."""
    body = "---\nschema_version: 99\nname: Ada\ntimezone: UTC\n---\n\n# Voice\nbe brief\n"
    (tmp_path / "personality.md").write_text(body)

    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "migrate"])
    assert result.exit_code != 0
    combined = result.output + (str(result.exception) if result.exception else "")
    assert "personality.md" in combined


def test_migrate_missing_personality_errors(tmp_path: Path) -> None:
    """Missing personality.md surfaces a clear error with the file path."""
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "migrate"])
    assert result.exit_code != 0
    combined = result.output + (str(result.exception) if result.exception else "")
    assert "personality.md" in combined


def test_migrate_missing_frontmatter_errors(tmp_path: Path) -> None:
    """A personality.md without YAML frontmatter surfaces a clear error."""
    (tmp_path / "personality.md").write_text("# Voice\nno frontmatter here\n")
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "migrate"])
    assert result.exit_code != 0
    combined = result.output + (str(result.exception) if result.exception else "")
    assert "personality.md" in combined
