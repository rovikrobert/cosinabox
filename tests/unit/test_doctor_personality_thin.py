from __future__ import annotations

from pathlib import Path

from cosinabox.doctor.checks import PersonalityThinCheck


def test_thin_personality_flagged(tmp_path: Path) -> None:
    (tmp_path / "personality.md").write_text(
        "---\nschema_version: 1\nname: A\ntimezone: UTC\n---\n\n# Voice\nbe direct\n"
    )
    check = PersonalityThinCheck()
    result = check.run(config_dir=tmp_path, history={})
    assert result.status == "fail"


def test_substantive_personality_passes(tmp_path: Path) -> None:
    body = "x" * 800
    (tmp_path / "personality.md").write_text(
        f"---\nschema_version: 1\nname: A\ntimezone: UTC\n---\n\n# Voice\n{body}\n"
    )
    check = PersonalityThinCheck()
    result = check.run(config_dir=tmp_path, history={})
    assert result.status == "pass"
