from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "cosinabox" / "templates" / "user-repo"
REPO_ROOT = Path(__file__).resolve().parents[2]
# Resolve the installed `cosinabox` entry point. Works in both activated venvs
# (shutil.which finds it on PATH) and bare `pip install -e` environments like CI
# (fall back to the Python interpreter's bin dir, where pip drops entry points).
COSINABOX_BIN = shutil.which("cosinabox") or str(Path(sys.executable).parent / "cosinabox")
COSINABOX_BIN_DIR = str(Path(COSINABOX_BIN).parent)


@pytest.fixture
def fresh_user_repo(tmp_path: Path) -> Path:
    dest = tmp_path / "cos"
    shutil.copytree(TEMPLATE, dest)
    subprocess.run(["git", "init"], cwd=dest, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=dest,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=dest,
        check=True,
        capture_output=True,
    )
    # Commit all template files so they are not in the staged diff for subsequent tests.
    # The secret scan only looks at staged (new/modified) files, so pre-existing files
    # that contain pattern strings as documentation are not scanned.
    subprocess.run(["git", "add", "."], cwd=dest, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: initial template"],
        cwd=dest,
        check=True,
        capture_output=True,
    )
    return dest


def _hook_env() -> dict[str, str]:
    """Build env with venv bin prepended so cosinabox is resolvable."""
    env = {**os.environ}
    original_path = env.get("PATH", "")
    env["PATH"] = f"{COSINABOX_BIN_DIR}:{original_path}"
    return env


def test_validate_passes_on_template(fresh_user_repo: Path) -> None:
    """Confirm that the template files pass cosinabox validate."""
    result = subprocess.run(
        [COSINABOX_BIN, "--config-dir", str(fresh_user_repo), "validate"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_secret_scan_blocks_anthropic_key(fresh_user_repo: Path) -> None:
    """Pre-commit hook must exit non-zero when an Anthropic API key is staged."""
    leaky = fresh_user_repo / "personality.md"
    leaky.write_text(leaky.read_text() + "\n\nDEBUG: sk-ant-12345\n")
    subprocess.run(
        ["git", "add", "personality.md"], cwd=fresh_user_repo, check=True, capture_output=True
    )

    env = _hook_env()
    # cosinabox validate reads from cwd by default; make sure it finds our config
    env["COSINABOX_CONFIG_DIR"] = str(fresh_user_repo)

    result = subprocess.run(
        ["bash", str(fresh_user_repo / ".cosinabox" / "pre-commit")],
        cwd=fresh_user_repo,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode != 0
    assert "secret" in (result.stdout + result.stderr).lower()


def test_clean_commit_passes_hook(fresh_user_repo: Path) -> None:
    """Pre-commit hook must exit zero when no secrets are present."""
    clean = fresh_user_repo / "personality.md"
    clean.write_text(clean.read_text() + "\n\n# Updated goals\n")
    subprocess.run(
        ["git", "add", "personality.md"], cwd=fresh_user_repo, check=True, capture_output=True
    )

    env = _hook_env()
    env["COSINABOX_CONFIG_DIR"] = str(fresh_user_repo)

    result = subprocess.run(
        ["bash", str(fresh_user_repo / ".cosinabox" / "pre-commit")],
        cwd=fresh_user_repo,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
