from __future__ import annotations
import subprocess
from pathlib import Path
from cosinabox.doctor.checks import BriefingDriftCheck, PrepNoiseCheck, SecretInTrackedFileCheck

def test_prep_noise_flagged() -> None:
    history = {"prep_fires_per_day": 12}
    check = PrepNoiseCheck()
    result = check.run(config_dir=Path("/tmp"), history=history)
    assert result.status == "fail"

def test_briefing_drift_when_override_unsimulated(tmp_path: Path) -> None:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "morning_briefing.md").write_text("custom prompt")
    history = {"simulate_log": []}
    check = BriefingDriftCheck()
    result = check.run(config_dir=tmp_path, history=history)
    assert result.status == "fail"

def test_secret_in_tracked_file_flagged(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    leaky = tmp_path / "personality.md"
    leaky.write_text("hello sk-ant-12345leakedkey end")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-m", "test", "--no-verify"], cwd=tmp_path, check=True, capture_output=True)
    check = SecretInTrackedFileCheck()
    result = check.run(config_dir=tmp_path, history={})
    assert result.status == "fail"
