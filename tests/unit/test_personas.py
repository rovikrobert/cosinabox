from __future__ import annotations

from importlib.resources import files


def test_founder_persona_has_required_sections() -> None:
    text = files("cosinabox.personas").joinpath("founder.md").read_text()
    assert "schema_version: 1" in text
    assert "# Voice" in text
    assert "# Stakes" in text
    assert "# Defaults" in text
