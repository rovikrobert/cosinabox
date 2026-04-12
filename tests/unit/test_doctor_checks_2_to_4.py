from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from cosinabox.doctor.checks import CostRunawayCheck, StakeholdersEmptyCheck, ToolLoopExcessCheck


def test_stakeholders_empty_after_7_days(tmp_path: Path) -> None:
    (tmp_path / "stakeholders.yaml").write_text(
        "schema_version: 1\nstakeholders:\n  - name: A\n    cadence: weekly\n"
    )
    check = StakeholdersEmptyCheck()
    history = {"installed_date": (date.today() - timedelta(days=10)).isoformat()}
    result = check.run(config_dir=tmp_path, history=history)
    assert result.status == "fail"


def test_stakeholders_empty_passes_with_3(tmp_path: Path) -> None:
    body = "schema_version: 1\nstakeholders:\n"
    for n in ("A", "B", "C"):
        body += f"  - name: {n}\n    cadence: weekly\n"
    (tmp_path / "stakeholders.yaml").write_text(body)
    check = StakeholdersEmptyCheck()
    history = {"installed_date": (date.today() - timedelta(days=10)).isoformat()}
    result = check.run(config_dir=tmp_path, history=history)
    assert result.status == "pass"


def test_cost_runaway_flagged(tmp_path: Path) -> None:
    history = {
        "daily_spend": {(date.today() - timedelta(days=i)).isoformat(): 13.0 for i in range(7)}
    }
    check = CostRunawayCheck()
    result = check.run(config_dir=tmp_path, history=history)
    assert result.status == "fail"


def test_tool_loop_excess_flagged(tmp_path: Path) -> None:
    history = {"avg_tool_iterations_per_message": 7.5}
    check = ToolLoopExcessCheck()
    result = check.run(config_dir=tmp_path, history=history)
    assert result.status == "fail"
