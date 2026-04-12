from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from cosinabox.doctor.checks import OAuthExpiringCheck, SchemaOutdatedCheck, StaleFollowupsCheck


def test_stale_followups_flagged(tmp_path: Path) -> None:
    body = "schema_version: 1\nstakeholders:\n"
    for i in range(25):
        old = (date.today() - timedelta(days=60)).isoformat()
        body += f"  - name: P{i}\n    cadence: weekly\n    last_contact: '{old}'\n"
    (tmp_path / "stakeholders.yaml").write_text(body)
    check = StaleFollowupsCheck()
    result = check.run(config_dir=tmp_path, history={})
    assert result.status == "fail"


def test_oauth_expiring_flagged() -> None:
    history = {"google_token_expires": (date.today() + timedelta(days=7)).isoformat()}
    check = OAuthExpiringCheck()
    result = check.run(config_dir=Path("/tmp"), history=history)
    assert result.status == "fail"


def test_schema_outdated_flagged(tmp_path: Path) -> None:
    (tmp_path / "stakeholders.yaml").write_text("schema_version: 0\nstakeholders: []\n")
    check = SchemaOutdatedCheck()
    result = check.run(config_dir=tmp_path, history={})
    assert result.status == "fail"
