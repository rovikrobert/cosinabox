from __future__ import annotations

from click.testing import CliRunner

from cosinabox.cli.main import cli


def test_init_then_interview_then_doctor(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runner = CliRunner()

    # 1. Init
    target = tmp_path / "my-cos"
    r = runner.invoke(cli, ["init", str(target)])
    assert r.exit_code == 0

    # 2. Interview, walking all 10 steps
    r = runner.invoke(cli, ["-C", str(target), "interview", "--start"])
    assert r.exit_code == 0
    canned = [
        "Alex, Founder, Loop AI, America/Los_Angeles",
        "Closing a Series A in 6 weeks.",
        "blunt",
        "Sarah Chen, Sequoia, weekly, replies in mornings",
        "lunch, focus block",
        "yes",
        "done",
        "yes default",
        "ok",
        "yes",
    ]
    for ans in canned:
        r = runner.invoke(cli, ["-C", str(target), "interview", "--answer", ans])
        assert r.exit_code == 0, r.output

    # 3. Doctor
    r = runner.invoke(cli, ["-C", str(target), "doctor", "--json"])
    import json

    data = json.loads(r.output)
    assert len(data) == 10
