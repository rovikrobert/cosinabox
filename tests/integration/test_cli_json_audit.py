from __future__ import annotations
import json
from pathlib import Path
from click.testing import CliRunner
from cosinabox.cli.main import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "tests" / "fixtures" / "sample-user-repo"

def test_validate_json_parses() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "validate", "--json"])
    json.loads(result.output)

def test_describe_json_parses() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "describe", "--json"])
    json.loads(result.output)

def test_doctor_json_parses() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(SAMPLE), "doctor", "--json"])
    json.loads(result.output)
