# Plan: `cosinabox doctor` actively probes refresh tokens (Initiative B)

> **For agentic workers:** Use `superpowers:executing-plans` or `superpowers:subagent-driven-development`. Steps use checkbox (`- [ ]`) syntax.

**Spec:** `docs/specs/2026-05-06-oauth-ux-rework.md`, "Initiative B".
**Branch:** `feat/doctor-oauth` at `~/.worktrees/cosinabox/feat-doctor-oauth`.
**How to resume:** open this file, find the first `- [ ]` checkbox, follow the milestone's steps. Plan is self-contained.

## Goal

Make `cosinabox doctor` actually exercise each configured Google refresh token (mint a fresh access token via `creds.refresh(Request())`) instead of only checking config-file presence and schema. Catch dead tokens *before* the next briefing renders empty data.

## Architecture

- New check class `OAuthRefreshLiveCheck` in `src/cosinabox/doctor/checks.py`. Loops `build_all_credentials()`, attempts `cred.refresh(Request())`, reports per-account.
- `Check` ABC gains a `network: bool = False` class attr. Existing checks default to False; the new one is True.
- `cosinabox doctor` gets a `--offline` flag that filters out network-requiring checks.
- Per-account email lookup: read `integrations.yaml` directly (mirror Initiative A's `_load_google_accounts`). Doctor doesn't start the App, so `set_account_emails()` global state is unavailable.
- Missing `[google]` extra → return `warn` ("install `cosinabox[google]`"), not `fail`. Doctor surfaces; an unconfigured optional extra isn't a failure.

## Tech Stack

Python 3.11+, existing `[google]` extras (`google-auth`, `google-api-python-client`), Click. Tests use `unittest.mock.patch` to stub `cred.refresh` — no real network from unit tests.

## Files

| Path | Action | Responsibility |
|---|---|---|
| `src/cosinabox/doctor/checks.py` | Modify | Add `OAuthRefreshLiveCheck`; add `network: bool = False` to `Check` ABC. |
| `src/cosinabox/doctor/registry.py` | Modify | Register the new check. |
| `src/cosinabox/cli/doctor.py` | Modify | Add `--offline` flag; filter checks by `network` attr. |
| `tests/unit/test_doctor_oauth_refresh_live.py` | Create | Unit tests for the new check (success, fail, ImportError, multi-account, email labels). |
| `tests/unit/test_cli_doctor.py` | Modify | Add `--offline` filter test. |

---

## M1 — Open questions sign-off

Five open questions surfaced and signed off in chat (2026-05-06):

| Q | Decision | Why |
|---|---|---|
| Email source at doctor-time | Read `integrations.yaml` directly | Doctor doesn't start the App; mirror `_load_google_accounts` |
| `--offline` mechanism | `network: bool` on `Check` ABC | Avoids per-check special-casing |
| `[google]` extra missing | Warn, not fail | Optional extra; doctor surfaces |
| Smoke discipline | M5a (structural, I run) + M5b (real-Google, maintainer) | New `feedback_cli_wrapper_smoke_test.md` rule |
| Fix message | Recommend `cosinabox auth refresh` (Initiative A) | A is shipped |

- [x] **Sign-off received in chat.** Proceed to M2.

**Estimate:** 0 (already done).

---

## M2 — Add `OAuthRefreshLiveCheck` + `network` attr on Check ABC

**Files:**
- Modify: `src/cosinabox/doctor/checks.py`
- Create: `tests/unit/test_doctor_oauth_refresh_live.py`

### Steps

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_doctor_oauth_refresh_live.py`

```python
"""Tests for OAuthRefreshLiveCheck — actively exercises refresh tokens.

All `cred.refresh()` calls are mocked; the test does not touch the
network. The integration test in tests/integration covers the real
network path (run on demand, not in CI).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from cosinabox.doctor.checks import OAuthRefreshLiveCheck


def _write_integrations(tmp_path: Path, accounts: list[dict[str, str]]) -> Path:
    cfg = {
        "schema_version": 1,
        "integrations": {"google": {"enabled": True, "accounts": accounts}},
    }
    (tmp_path / "integrations.yaml").write_text(yaml.safe_dump(cfg))
    return tmp_path


def test_check_is_marked_network() -> None:
    """OAuthRefreshLiveCheck must declare network=True so --offline skips it."""
    assert OAuthRefreshLiveCheck.network is True


def test_pass_when_all_creds_refresh_successfully(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])
    fake_cred = MagicMock()
    fake_cred.refresh = MagicMock(return_value=None)

    with patch(
        "cosinabox.doctor.checks.build_all_credentials",
        return_value=[fake_cred],
    ):
        result = OAuthRefreshLiveCheck().run(config_dir=cfg_dir, history={})

    assert result.status == "pass"
    assert "rovik@example.com" in result.message


def test_fail_when_one_cred_refresh_raises(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(
        tmp_path,
        [{"email": "ok@example.com"}, {"email": "dead@example.com"}],
    )
    from google.auth.exceptions import RefreshError

    ok = MagicMock()
    ok.refresh = MagicMock(return_value=None)
    bad = MagicMock()
    bad.refresh = MagicMock(side_effect=RefreshError("token has been expired or revoked"))

    with patch(
        "cosinabox.doctor.checks.build_all_credentials",
        return_value=[ok, bad],
    ):
        result = OAuthRefreshLiveCheck().run(config_dir=cfg_dir, history={})

    assert result.status == "fail"
    # Failure message identifies the bad account by email and points at the fix.
    assert "dead@example.com" in result.message
    assert "cosinabox auth refresh" in result.message
    # The healthy account is NOT mentioned in the failure message — only the
    # failing one(s) — so the fix instruction stays focused.
    assert "ok@example.com" not in result.message


def test_warn_when_google_extras_not_installed(tmp_path: Path) -> None:
    """Missing [google] extra → warn, not fail. Doctor surfaces; optional
    extras are explicitly opt-in.
    """
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])

    from cosinabox.tools.google.auth import GoogleAuthError

    with patch(
        "cosinabox.doctor.checks.build_all_credentials",
        side_effect=GoogleAuthError(
            "Missing GOOGLE_OAUTH_CLIENT_ID or GOOGLE_OAUTH_CLIENT_SECRET. "
            "Run `cosinabox auth google` to configure."
        ),
    ):
        result = OAuthRefreshLiveCheck().run(config_dir=cfg_dir, history={})

    assert result.status == "warn"
    assert "google" in result.message.lower()


def test_warn_when_google_integration_not_enabled(tmp_path: Path) -> None:
    """If integrations.yaml has google.enabled=false, the check has nothing
    to probe. Warn rather than fail — the user opted out."""
    cfg = {"schema_version": 1, "integrations": {"google": {"enabled": False}}}
    (tmp_path / "integrations.yaml").write_text(yaml.safe_dump(cfg))

    result = OAuthRefreshLiveCheck().run(config_dir=tmp_path, history={})
    assert result.status == "warn"
    assert "not enabled" in result.message.lower() or "disabled" in result.message.lower()


def test_failure_message_uses_account_index_when_email_missing(tmp_path: Path) -> None:
    """Edge: integrations.yaml missing or accounts list empty, but
    build_all_credentials returns creds (e.g. legacy single-account env vars).
    Fall back to '#1', '#2' labels so the message is still actionable.
    """
    # Empty integrations.yaml — but credentials exist (legacy env-var path).
    (tmp_path / "integrations.yaml").write_text(
        "schema_version: 1\nintegrations:\n  google:\n    enabled: true\n"
    )
    from google.auth.exceptions import RefreshError

    bad = MagicMock()
    bad.refresh = MagicMock(side_effect=RefreshError("revoked"))

    with patch(
        "cosinabox.doctor.checks.build_all_credentials",
        return_value=[bad],
    ):
        result = OAuthRefreshLiveCheck().run(config_dir=tmp_path, history={})

    assert result.status == "fail"
    assert "#1" in result.message or "account 1" in result.message.lower()
    assert "cosinabox auth refresh" in result.message


def test_transient_error_returns_warn_not_fail(tmp_path: Path) -> None:
    """A network blip (TransportError, etc.) is not a "token is dead" signal
    — surface as warn so the user knows something happened but doesn't
    panic-rotate a healthy token.
    """
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])
    from google.auth.exceptions import TransportError

    bad = MagicMock()
    bad.refresh = MagicMock(side_effect=TransportError("connection reset"))

    with patch(
        "cosinabox.doctor.checks.build_all_credentials",
        return_value=[bad],
    ):
        result = OAuthRefreshLiveCheck().run(config_dir=cfg_dir, history={})

    assert result.status == "warn"
    assert "transient" in result.message.lower() or "network" in result.message.lower()
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd ~/.worktrees/cosinabox/feat-doctor-oauth
.venv/bin/pytest tests/unit/test_doctor_oauth_refresh_live.py -v
```

Expected: all fail with `ImportError: cannot import name 'OAuthRefreshLiveCheck'`.

- [ ] **Step 3: Add `network` attr to `Check` ABC** in `src/cosinabox/doctor/checks.py`

Add to the `Check` class definition:

```python
class Check(ABC):
    name: str
    severity: str = "warn"
    # Whether this check requires network access. The CLI's --offline flag
    # filters these out so doctor can run in CI / on planes without
    # spurious failures.
    network: bool = False

    @abstractmethod
    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult: ...
```

- [ ] **Step 4: Implement `OAuthRefreshLiveCheck`** in `src/cosinabox/doctor/checks.py`

Append at the end of the file:

```python
class OAuthRefreshLiveCheck(Check):
    """Mint a fresh access token for each configured Google account.

    Catches dead refresh tokens proactively instead of waiting for the
    next morning_briefing to render an empty calendar. Live network
    check — gated behind --offline.
    """

    name = "oauth_refresh_live"
    severity = "fail"
    network = True

    def run(self, *, config_dir: Path, history: dict[str, Any]) -> CheckResult:
        # Load configured account emails (for the failure message). Doctor
        # doesn't start the App, so we read integrations.yaml directly.
        integrations_path = config_dir / "integrations.yaml"
        emails: list[str] = []
        google_enabled = False
        if integrations_path.exists():
            raw = yaml.safe_load(integrations_path.read_text()) or {}
            integrations = raw.get("integrations", {}) if isinstance(raw, dict) else {}
            google = integrations.get("google", {}) if isinstance(integrations, dict) else {}
            if isinstance(google, dict):
                google_enabled = bool(google.get("enabled"))
                accounts = google.get("accounts") or []
                if isinstance(accounts, list):
                    emails = [
                        str(a["email"])
                        for a in accounts
                        if isinstance(a, dict) and isinstance(a.get("email"), str)
                    ]

        if not google_enabled:
            return CheckResult(
                self.name,
                "warn",
                "Google integration not enabled in integrations.yaml; nothing to probe.",
            )

        # Late import: keeps this module loadable when [google] extras
        # are missing.
        try:
            from cosinabox.tools.google.auth import (
                GoogleAuthError,
                build_all_credentials,
            )
        except ImportError:
            return CheckResult(
                self.name,
                "warn",
                "[google] extras not installed; install `cosinabox[google]` to enable this check.",
            )

        try:
            creds = list(build_all_credentials())
        except GoogleAuthError as e:
            return CheckResult(
                self.name,
                "warn",
                f"Could not build credentials: {e}",
            )

        from google.auth.exceptions import RefreshError, TransportError
        from google.auth.transport.requests import Request

        request = Request()
        failed: list[str] = []
        transient: list[str] = []
        for i, cred in enumerate(creds, start=1):
            label = emails[i - 1] if 0 < i <= len(emails) else f"#{i}"
            try:
                cred.refresh(request)
            except RefreshError:
                failed.append(label)
            except TransportError:
                transient.append(label)
            except Exception:  # noqa: BLE001 — preserve healthy creds' status
                transient.append(label)

        if failed:
            return CheckResult(
                self.name,
                "fail",
                f"Refresh failed for: {', '.join(failed)}. "
                f"Run: cosinabox auth refresh",
            )
        if transient:
            return CheckResult(
                self.name,
                "warn",
                f"Transient network error refreshing: {', '.join(transient)}. "
                "Retry in a moment.",
            )
        if not creds:
            return CheckResult(
                self.name, "warn", "No Google credentials configured."
            )
        return CheckResult(
            self.name,
            "pass",
            f"All {len(creds)} Google account(s) refreshed cleanly.",
        )
```

Add `from cosinabox.tools.google.auth import build_all_credentials` import only where the test patches it (`cosinabox.doctor.checks.build_all_credentials`). That means we import `build_all_credentials` at module top-level too, so the test's `patch("cosinabox.doctor.checks.build_all_credentials", ...)` works. **Use a try/except wrapper at module top for the import** so the module still loads when `[google]` is missing:

```python
# At top of checks.py, alongside other imports:
try:
    from cosinabox.tools.google.auth import build_all_credentials
except ImportError:  # [google] extras not installed
    build_all_credentials = None  # type: ignore[assignment]
```

Then in the check, use the late import path (already shown above) — but the test patch target `cosinabox.doctor.checks.build_all_credentials` still resolves because the symbol exists at module level (either as the real function or as `None`). The check's late `try: from ... import` re-imports for runtime use, and the patch overrides the module-level binding. Test assertions remain stable.

- [ ] **Step 5: Run the tests to verify green**

```bash
.venv/bin/pytest tests/unit/test_doctor_oauth_refresh_live.py -v
```

Expected: all pass.

- [ ] **Step 6: Run full suite**

```bash
.venv/bin/pytest tests/unit/ -q
```

Expected: green (existing checks unchanged; new `network` attr defaults to False).

- [ ] **Step 7: Lint + types**

```bash
.venv/bin/ruff check src tests
.venv/bin/mypy src/cosinabox
```

- [ ] **Step 8: Commit**

```bash
git add src/cosinabox/doctor/checks.py tests/unit/test_doctor_oauth_refresh_live.py
git commit -m "feat(doctor): OAuthRefreshLiveCheck — actively probe refresh tokens

Plan: 2026-05-06-doctor-oauth-probe, M2. Initiative B of OAuth UX
spec.

New check loops build_all_credentials(), attempts cred.refresh() per
account, reports pass/fail/warn with email labels read from
integrations.yaml. RefreshError → fail with 'cosinabox auth refresh'
hint; TransportError → warn (don't panic-rotate healthy tokens on
network blips); GoogleAuthError / missing [google] extra → warn.

Adds network: bool attr to Check ABC so the next milestone's --offline
flag can filter."
```

**Estimate:** 45 min.

---

## M3 — Wire `--offline` flag to doctor CLI

**Files:**
- Modify: `src/cosinabox/cli/doctor.py`
- Modify: `tests/unit/test_cli_doctor.py`

### Steps

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_cli_doctor.py`)

```python
def test_doctor_offline_skips_network_checks(tmp_path: Path) -> None:
    """--offline must filter out checks where network=True. The output
    should NOT include the live OAuth check's name.
    """
    from click.testing import CliRunner

    from cosinabox.cli.main import cli

    # Minimal fixture so doctor doesn't bail on missing personality.
    (tmp_path / "personality.md").write_text("---\nname: x\n---\nPlaceholder body.")

    result = CliRunner().invoke(cli, ["-C", str(tmp_path), "doctor", "--offline"])
    assert "oauth_refresh_live" not in result.output


def test_doctor_default_includes_network_checks(tmp_path: Path) -> None:
    """Without --offline, the live OAuth check must be in the run set,
    even if it warns/fails on a fixture without creds.
    """
    from click.testing import CliRunner

    from cosinabox.cli.main import cli

    (tmp_path / "personality.md").write_text("---\nname: x\n---\nPlaceholder body.")

    result = CliRunner().invoke(cli, ["-C", str(tmp_path), "doctor"])
    assert "oauth_refresh_live" in result.output
```

- [ ] **Step 2: Run to confirm fails**

```bash
.venv/bin/pytest tests/unit/test_cli_doctor.py -v -k "offline or default"
```

Expected: both fail (`--offline` flag doesn't exist yet; check isn't registered yet).

- [ ] **Step 3: Edit `src/cosinabox/cli/doctor.py`**

Add the `--offline` flag and filter the registry:

```python
"""`cosinabox doctor`."""

from __future__ import annotations

import json as jsonlib
from pathlib import Path
from typing import Any

import click

from cosinabox.doctor.registry import REGISTRY


def _load_history(config_dir: Path) -> dict[str, Any]:
    path = config_dir / ".cosinabox" / "history.json"
    if path.exists():
        try:
            data = jsonlib.loads(path.read_text())
            return data if isinstance(data, dict) else {}
        except jsonlib.JSONDecodeError:
            return {}
    return {}


@click.command("doctor")
@click.option("--json", "json_out", is_flag=True)
@click.option(
    "--offline",
    is_flag=True,
    default=False,
    help="Skip checks that require network access (e.g. live OAuth probe).",
)
@click.pass_context
def doctor_cmd(ctx: click.Context, json_out: bool, offline: bool) -> None:
    """Run all health checks."""
    config_dir: Path = ctx.obj["config_dir"]
    history = _load_history(config_dir)
    checks = [c for c in REGISTRY if not (offline and c.network)]
    results = [c.run(config_dir=config_dir, history=history) for c in checks]
    if json_out:
        click.echo(
            jsonlib.dumps(
                [{"name": r.name, "status": r.status, "message": r.message} for r in results],
                indent=2,
            )
        )
    else:
        for r in results:
            icon = {"pass": "OK", "warn": "WARN", "fail": "FAIL"}.get(r.status, "?")
            click.echo(f"[{icon}] {r.name}: {r.message}")
    if any(r.status == "fail" for r in results):
        ctx.exit(1)
```

- [ ] **Step 4: Run tests** (M3's tests will still fail until M4 registers the check, but `--offline` filtering is now testable indirectly via existing tests).

```bash
.venv/bin/pytest tests/unit/test_cli_doctor.py -v
```

Some tests pass (the new `--offline` flag exists), the new ones fail until M4. That's fine — these are integration tests; M4 closes the loop.

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/cli/doctor.py tests/unit/test_cli_doctor.py
git commit -m "feat(doctor): --offline flag filters network-requiring checks

Plan: 2026-05-06-doctor-oauth-probe, M3.
Skips Check instances where network=True, so doctor can run in CI /
on planes without spurious failures from the live OAuth probe (or
any future network-bearing check)."
```

**Estimate:** 20 min.

---

## M4 — Register the new check

**Files:**
- Modify: `src/cosinabox/doctor/registry.py`

### Steps

- [ ] **Step 1: Edit `src/cosinabox/doctor/registry.py`**

```python
"""Doctor check registry."""

from __future__ import annotations

from cosinabox.doctor.checks import (
    BriefingDriftCheck,
    Check,
    CostRunawayCheck,
    OAuthExpiringCheck,
    OAuthRefreshLiveCheck,
    PersonalityThinCheck,
    PrepNoiseCheck,
    SchemaOutdatedCheck,
    SecretInTrackedFileCheck,
    StakeholdersEmptyCheck,
    StaleFollowupsCheck,
    ToolLoopExcessCheck,
)

REGISTRY: list[Check] = [
    PersonalityThinCheck(),
    StakeholdersEmptyCheck(),
    CostRunawayCheck(),
    ToolLoopExcessCheck(),
    PrepNoiseCheck(),
    BriefingDriftCheck(),
    SecretInTrackedFileCheck(),
    StaleFollowupsCheck(),
    OAuthExpiringCheck(),
    OAuthRefreshLiveCheck(),  # network=True; gated by --offline
    SchemaOutdatedCheck(),
]
```

- [ ] **Step 2: Run all doctor tests**

```bash
.venv/bin/pytest tests/unit/ -k doctor -v
```

Expected: M3's two new tests now pass; existing doctor tests stay green.

- [ ] **Step 3: Run the full unit suite**

```bash
.venv/bin/pytest tests/unit/ -q
```

Expected: all green.

- [ ] **Step 4: Lint + types**

```bash
.venv/bin/ruff check src tests
.venv/bin/mypy src/cosinabox
```

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/doctor/registry.py
git commit -m "feat(doctor): register OAuthRefreshLiveCheck

Plan: 2026-05-06-doctor-oauth-probe, M4.
Wires the new check into the global REGISTRY so cosinabox doctor
exercises refresh tokens by default (--offline opts out)."
```

**Estimate:** 10 min.

---

## M5a — Structural smoke (Claude runs)

**Files:**
- None (verification only).

**Why:** Per the new feedback memory `feedback_cli_wrapper_smoke_test.md`, every CLI-wrapper plan needs a real-binary smoke before merge. Mocked unit tests don't catch schema drift. For this plan, the "external surface" is the Google OAuth refresh endpoint — but exercising it needs valid creds. M5a covers what can be verified without real creds; M5b (next milestone, maintainer-run) covers the real-creds path.

### Steps

- [ ] **Step 1: Smoke against a fixture user-repo with no creds.** Confirm the check warns gracefully.

```bash
mkdir -p /tmp/cos-doctor-smoke && cat > /tmp/cos-doctor-smoke/integrations.yaml <<'EOF'
schema_version: 1
integrations:
  google:
    enabled: true
    accounts:
      - email: smoketest@example.com
EOF
echo "---" > /tmp/cos-doctor-smoke/personality.md
echo "name: smoke" >> /tmp/cos-doctor-smoke/personality.md
echo "---" >> /tmp/cos-doctor-smoke/personality.md
echo "Placeholder." >> /tmp/cos-doctor-smoke/personality.md

# No GOOGLE_OAUTH_* env vars → expect warn, not fail.
unset GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_CLIENT_SECRET GOOGLE_OAUTH_REFRESH_TOKEN
unset GOOGLE_OAUTH_REFRESH_TOKEN_1 GOOGLE_OAUTH_REFRESH_TOKEN_2

.venv/bin/cosinabox -C /tmp/cos-doctor-smoke doctor --json | jq '.[] | select(.name == "oauth_refresh_live")'
```

Expected JSON: `{"name": "oauth_refresh_live", "status": "warn", "message": "..."}`. The message should mention missing creds, not crash.

- [ ] **Step 2: Smoke with intentionally-bad creds → expect fail.**

```bash
GOOGLE_OAUTH_CLIENT_ID=dummy \
GOOGLE_OAUTH_CLIENT_SECRET=dummy \
GOOGLE_OAUTH_REFRESH_TOKEN_1=intentionally-invalid-token \
.venv/bin/cosinabox -C /tmp/cos-doctor-smoke doctor --json | jq '.[] | select(.name == "oauth_refresh_live")'
```

Expected: `{"status": "fail", "message": "...auth refresh..."}` referencing `smoketest@example.com`.

- [ ] **Step 3: Confirm `--offline` skips it.**

```bash
.venv/bin/cosinabox -C /tmp/cos-doctor-smoke doctor --offline --json | jq '[.[].name] | contains(["oauth_refresh_live"])'
```

Expected: `false`.

- [ ] **Step 4: Cleanup.**

```bash
rm -rf /tmp/cos-doctor-smoke
```

- [ ] **Step 5: Note results in PR description.** Quote the actual `--json` output from steps 1–3.

**Estimate:** 15 min.

---

## M5b — Real Google API smoke (maintainer runs)

**Why:** This is the load-bearing test that the new feedback memory mandates. Doctor's whole point is exercising real refresh tokens; until we run the check against a real Google account, the implementation is unverified. **Do NOT merge the PR until M5b passes.**

### Steps (maintainer)

- [ ] **Step 1:** From the maintainer's user-repo directory (e.g. `~/code/rovik-keevs`) with `.env` populated and `cosinabox` installed at this branch:

```bash
cosinabox doctor --json | jq '.[] | select(.name == "oauth_refresh_live")'
```

- [ ] **Step 2:** Verify the output:
  - **Healthy account** → `{"status": "pass", "message": "All N Google account(s) refreshed cleanly."}`
  - **One dead account** → `{"status": "fail", "message": "Refresh failed for: <email>. Run: cosinabox auth refresh"}`
  - The dead-account email is the one `auth_health` is currently flagging in Telegram.

- [ ] **Step 3:** If the output disagrees with reality (e.g. all-pass when `auth_health` says one account is dead), investigate before merging. Likely culprits:
  - `build_all_credentials()` order doesn't match `integrations.yaml` order → email label is wrong.
  - `cred.refresh()` doesn't raise on a revoked token (silently mints a stale-but-non-error response).

- [ ] **Step 4:** Reply on the PR with the exact `--json` output and a green light.

**Estimate:** 5 min, once Claude has shipped the PR.

---

## M6 — PR + retro

### Steps

- [ ] **Step 1: Final pre-PR check.**

```bash
.venv/bin/pytest tests/ -q
.venv/bin/ruff check src tests
.venv/bin/mypy src/cosinabox
```

Expected: all green.

- [ ] **Step 2: Push the branch.**

```bash
git push -u origin feat/doctor-oauth
```

- [ ] **Step 3: Open the PR with M5b explicitly named as a required gate.**

```bash
gh pr create \
  --title "feat(doctor): cosinabox doctor probes refresh tokens (Initiative B)" \
  --body "$(cat <<'EOF'
## Summary
- New `OAuthRefreshLiveCheck` exercises every configured Google refresh token via `cred.refresh(Request())`. Catches dead tokens before the next briefing renders empty data.
- Adds `network: bool` to `Check` ABC + `--offline` flag to `cosinabox doctor` so CI / planes / no-internet contexts can skip cleanly.
- Failure message names the dead account by email (read from `integrations.yaml`) and points at `cosinabox auth refresh` as the fix.
- Missing `[google]` extras → warn, not fail.

Initiative B of `docs/specs/2026-05-06-oauth-ux-rework.md`. Plan: `docs/plans/2026-05-06-doctor-oauth-probe.md`.

## Test plan
- [x] Unit: 7 new tests in `test_doctor_oauth_refresh_live.py` + 2 new in `test_cli_doctor.py`. All green.
- [x] Lint + types clean.
- [x] **M5a structural smoke** (Claude ran): no-creds → warn; intentionally-bad creds → fail with the right email + fix command; `--offline` skips. Quoted JSON in retro doc.
- [ ] **M5b real Google API smoke** (maintainer): run `cosinabox doctor --json | jq '.[] | select(.name == "oauth_refresh_live")'` against your user-repo with live `.env` creds. Expected: `pass` for healthy accounts, `fail` for the account `auth_health` is currently Telegramming. **Do NOT merge until you've replied here with the JSON output.** New feedback memory `feedback_cli_wrapper_smoke_test.md` codified this rule from PR #87's stress-test cycle.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: Wait for maintainer to run M5b and reply on the PR.** When confirmed:

```bash
gh pr merge --auto --squash --delete-branch
```

- [ ] **Step 5: Write the retro** at `docs/retros/2026-05-06-doctor-oauth-probe-retro.md`. Cover:
  1. What shipped vs planned.
  2. Estimate calibration (was 70%-of-plan still right?).
  3. Did M5b find anything M5a missed? (Most important data point — validates or invalidates the smoke discipline.)

- [ ] **Step 6: Commit retro on `main` after PR merges, and clean up worktree.**

```bash
git -C /Users/rovikrobert/code/cosinabox checkout main
git -C /Users/rovikrobert/code/cosinabox pull
git -C /Users/rovikrobert/code/cosinabox add docs/retros/2026-05-06-doctor-oauth-probe-retro.md
git -C /Users/rovikrobert/code/cosinabox commit -m "docs(retro): doctor-oauth-probe"
git -C /Users/rovikrobert/code/cosinabox push
git -C /Users/rovikrobert/code/cosinabox worktree remove ~/.worktrees/cosinabox/feat-doctor-oauth
```

**Estimate:** 15 min (excluding wait time for M5b).

---

## Out of scope / follow-ups

- **Initiative C** (`/status` per-account auth + alert enrichment) — separate plan, ships next.
- **Initiative D** (web-based OAuth flow served by the bot) — v0.2.
- **`--offline` in CI**: the project's `.github/workflows/test.yml` already runs `pytest`, not `cosinabox doctor`; no CI change needed for this PR. If we later add a doctor smoke to CI, use `--offline`.
- **Per-check timeout for the refresh call** (e.g., a 5-second cap so a hung Google endpoint doesn't stall doctor). Defer until someone reports a hang in practice.
- **Caching the refresh-check result for N minutes** (so back-to-back `cosinabox doctor` runs don't hammer Google). Defer; doctor isn't a hot-path tool.
