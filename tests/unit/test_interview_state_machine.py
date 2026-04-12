from __future__ import annotations
from pathlib import Path
import yaml
from cosinabox.interview.state_machine import InterviewMachine

def test_machine_starts_at_step_1(tmp_path: Path) -> None:
    m = InterviewMachine(config_dir=tmp_path)
    m.start()
    q = m.next_question()
    assert "name" in q.lower() or "identity" in q.lower()
    assert m.current_step_index == 0

def test_step_1_writes_personality_frontmatter(tmp_path: Path) -> None:
    m = InterviewMachine(config_dir=tmp_path)
    m.start()
    m.answer("Alex Smith, Founder, Loop AI, America/Los_Angeles")
    text = (tmp_path / "personality.md").read_text()
    assert "Alex Smith" in text
    assert "America/Los_Angeles" in text

def test_machine_completes_after_10_steps(tmp_path: Path) -> None:
    m = InterviewMachine(config_dir=tmp_path)
    m.start()
    canned_answers = [
        "Alex, Founder, Loop AI, America/Los_Angeles",
        "Closing a Series A in 6 weeks.",
        "blunt",
        "Sarah Chen, Sequoia, weekly, replies in mornings",
        "skip lunch and focus blocks",
        "yes, only morning_briefing and pre_meeting_prep",
        "done",
        "yes default cap",
        "ok",
        "yes deploy",
    ]
    for a in canned_answers:
        m.answer(a)
    assert m.is_complete()
    assert (tmp_path / "personality.md").exists()
    sk = yaml.safe_load((tmp_path / "stakeholders.yaml").read_text())
    assert any(s["name"] == "Sarah Chen" for s in sk["stakeholders"])
