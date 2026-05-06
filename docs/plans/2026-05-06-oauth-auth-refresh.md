# Plan: `cosinabox auth refresh` (Initiative A of OAuth UX rework)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/specs/2026-05-06-oauth-ux-rework.md` (sections "Problem", "Goals", "Initiative A" are load-bearing).
**Status:** Draft. **Do not start M2 until the maintainer signs off on the open questions in M1.**
**Branch / worktree:** `feat/auth-refresh` at `~/.worktrees/cosinabox/feat-auth-refresh`.
**How to resume:** open this file, find the first `- [ ]` checkbox, read the surrounding milestone's "Files" + "Why" + "Steps" sections, start there. The plan is self-contained — do not rely on chat context.

## Goal

One command — `cosinabox auth refresh` — that collapses the ten-step manual re-auth flow into a guided, in-process orchestration: pick an account, pull OAuth client creds from the deploy, run consent, push the new refresh token back to the deploy, redeploy, verify.

## Architecture

- **One new orchestrator module** `src/cosinabox/cli/auth_refresh.py` — the Click command + the orchestration logic.
- **One thin deploy-target adapter** `src/cosinabox/cli/_railway.py` — subprocess wrappers around the `railway` CLI (whoami, status, variables get/set, up/redeploy, logs). Private (leading underscore) — when AWS/Fly land, a sibling `_aws.py` and a tiny dispatcher replace this. No premature abstraction; we'll grow the seam when we need it.
- **One small refactor in `cli/auth_google.py`** — extract the consent-and-mint logic into `mint_refresh_token(client_id, client_secret, expected_email) -> str` so `auth refresh` can call it directly instead of shelling out to its own subcommand.
- **No changes to `tools/google/auth.py`, `jobs/auth_health.py`, the schema, or any user-facing config files.** This is a wrapper, not a rewrite.

## Tech Stack

Python 3.11+, Click, `subprocess` (Railway CLI), existing `google-auth-oauthlib` (already a `[google]` extra). Tests use Click's `CliRunner` + `unittest.mock` — same pattern as `test_cli_auth_google.py`.

## Files

| Path | Action | Responsibility |
|---|---|---|
| `src/cosinabox/cli/auth_refresh.py` | Create | Click `auth refresh` subcommand + orchestration. |
| `src/cosinabox/cli/_railway.py` | Create | Thin Railway CLI subprocess adapter. |
| `src/cosinabox/cli/auth_google.py` | Modify | Extract `mint_refresh_token()` helper; CLI command becomes a thin wrapper. |
| `src/cosinabox/cli/main.py` | Modify | Register `auth_refresh_cmd` onto the existing `auth_cmd` group. |
| `tests/unit/test_cli_auth_refresh.py` | Create | Orchestrator tests — happy path + failure modes (the six from the spec). |
| `tests/unit/test_cli_railway_adapter.py` | Create | Railway adapter unit tests with `subprocess` mocked. |
| `tests/unit/test_cli_auth_google.py` | Modify | Add tests for the new `mint_refresh_token()` helper; existing tests stay green. |
| `src/cosinabox/templates/user-repo/docs/agent/oauth-walkthrough.md` | Modify | Lead with `cosinabox auth refresh`; keep the manual ten-step flow as fallback. |

---

## M1 — Open questions checkpoint (read first; do not skip)

The spec leaves four design calls to this plan. Each has a recommended answer below, derived from the existing codebase. **Maintainer must sign off (or correct) before M2 begins.** This is the only milestone with no code.

### Q1: Where does the command live? Naming collisions?

- **Recommendation:** `src/cosinabox/cli/auth_refresh.py` defining `auth_refresh_cmd`. Register onto the existing `auth_cmd` group from `cli/main.py` via `auth_cmd.add_command(auth_refresh_cmd)`. No new package, no group restructuring — three similar lines beats a premature `cli/auth/` package.
- **Verified:** No file at `cli/auth_refresh.py`; no symbol named `auth_refresh*` anywhere in the tree.
- **Tradeoff:** If a third `auth ...` subcommand lands (Initiative D's web flow probably will), the right-then move is to package up `cli/auth/`. Not now.

### Q2: Single vs multi-account picker UX

- **Recommendation:** If `integrations.yaml` has exactly one Google account, **skip the picker** — auto-select and print `Refreshing token for <email>...` so the user sees what was chosen. Picker only fires when `len(accounts) >= 2`. Add a `--account <email>` flag for non-interactive override (matches the existing `auth google --account` ergonomic).
- **Why:** Asking a question with one answer is a UX bug. Visible auto-selection is honest.

### Q3: Wrong-deploy-target detection

- **Recommendation:** Three layered checks before any mutation, each with a copy-pasteable fix in the error:
  1. `shutil.which("railway")` — if missing: `Railway CLI not installed. Install: https://docs.railway.com/guides/cli`
  2. `railway whoami` — if non-zero exit: `Not logged in to Railway. Run: railway login`
  3. `railway status --json` — if no `service` field: `No Railway service linked in <cwd>. Run: railway link`
- **Plus a confirmation gate:** print the detected `project / service` and prompt `Continue? [y/N]` (skipped with `--yes`). This catches "ran from the wrong user-repo directory" — the failure mode the spec calls out.

### Q4: Redeploy wait — tail logs in-process, or fire-and-return?

- **Recommendation:** **Fire-and-poll-deploy-status, do not tail logs.** Trigger the redeploy, poll `railway status --json` (5-min timeout) for the deployment to reach `SUCCESS`. Then print:
  > Redeploy succeeded. The next `auth_health` tick (≤15 min) will confirm the new token works. You'll get a Telegram alert if it doesn't.
- **Why not tail logs:** Tailing `railway logs` and parsing for the next `auth_health` line means we own a noisy stream parser that breaks the moment the log format changes. The next `auth_health` tick will Telegram the maintainer if the token is wrong — that's the verification path the spec already gives us. Initiative A's job is "make re-auth tractable", not "replace `auth_health`."
- **Flag:** `--no-wait` to skip the deploy-status poll entirely (returns after the redeploy is kicked off).
- **If maintainer disagrees:** spec says log-tailing; we can implement that in a follow-up plan instead of expanding this one. Surgical scope.

### Q5 (bonus, surfaced from code review): Legacy `GOOGLE_OAUTH_REFRESH_TOKEN` (no `_N`)

`build_all_credentials()` in `tools/google/auth.py:62-95` falls back to the unsuffixed `GOOGLE_OAUTH_REFRESH_TOKEN` when no `_1`, `_2`, ... vars exist. Some early deployments may still use that.

- **Recommendation:** Always write `GOOGLE_OAUTH_REFRESH_TOKEN_<N>` (positional, `accounts[i]` ↔ `_<i+1>`). If the Railway env has the legacy unsuffixed var, surface a one-time warning:
  > Your deploy uses the legacy `GOOGLE_OAUTH_REFRESH_TOKEN` (no number). Writing the new token to `GOOGLE_OAUTH_REFRESH_TOKEN_1`. You can delete `GOOGLE_OAUTH_REFRESH_TOKEN` after the next briefing succeeds.
- **No automatic deletion.** Deletion is destructive and reversible only by re-pasting the old value. Tell the user; let them clean up.

### Action

- [ ] **Maintainer sign-off:** Read Q1–Q5 above. Reply with "Q1 yes / Q2 yes / Q3 yes / Q4 yes / Q5 yes" (or override any). Then proceed to M2.

**Estimate:** 5 min (review only).

---

## M2 — Extract `mint_refresh_token` helper from `auth_google.py`

**Why:** `auth refresh` needs to run the same consent flow `auth google` already runs, but it can't shell out to itself cleanly (subprocess loses the local browser context, doubles the env-var setup). Extracting the core into a function lets both surfaces share the code path. Tests for the new helper are net-new; existing CLI tests must stay green untouched.

**Files:**
- Modify: `src/cosinabox/cli/auth_google.py`
- Test (modify): `tests/unit/test_cli_auth_google.py`

### Steps

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_cli_auth_google.py`)

```python
# --- mint_refresh_token() helper (extracted for `auth refresh` reuse) ---


def test_mint_refresh_token_returns_token_when_no_account_check() -> None:
    from cosinabox.cli.auth_google import mint_refresh_token

    fake_flow = MagicMock()
    fake_creds = MagicMock(refresh_token="rt-helper")
    fake_flow.run_local_server.return_value = fake_creds
    with patch(
        "cosinabox.cli.auth_google.InstalledAppFlow.from_client_config",
        return_value=fake_flow,
    ):
        token = mint_refresh_token(client_id="cid", client_secret="sec", expected_email=None)
    assert token == "rt-helper"


def test_mint_refresh_token_match_returns_token() -> None:
    from cosinabox.cli.auth_google import mint_refresh_token

    fake_flow = MagicMock()
    fake_flow.run_local_server.return_value = MagicMock(refresh_token="rt-match")
    with (
        patch(
            "cosinabox.cli.auth_google.InstalledAppFlow.from_client_config",
            return_value=fake_flow,
        ),
        patch(
            "cosinabox.cli.auth_google._consented_email",
            return_value="rovik@example.com",
        ),
    ):
        token = mint_refresh_token(
            client_id="cid", client_secret="sec", expected_email="rovik@example.com"
        )
    assert token == "rt-match"


def test_mint_refresh_token_mismatch_raises() -> None:
    from cosinabox.cli.auth_google import AccountMismatchError, mint_refresh_token

    fake_flow = MagicMock()
    fake_flow.run_local_server.return_value = MagicMock(refresh_token="rt-bad")
    with (
        patch(
            "cosinabox.cli.auth_google.InstalledAppFlow.from_client_config",
            return_value=fake_flow,
        ),
        patch(
            "cosinabox.cli.auth_google._consented_email",
            return_value="someone-else@example.com",
        ),
        pytest.raises(AccountMismatchError) as exc,
    ):
        mint_refresh_token(
            client_id="cid", client_secret="sec", expected_email="rovik@example.com"
        )
    msg = str(exc.value)
    assert "someone-else@example.com" in msg
    assert "rovik@example.com" in msg


def test_mint_refresh_token_unverifiable_raises() -> None:
    from cosinabox.cli.auth_google import AccountUnverifiableError, mint_refresh_token

    fake_flow = MagicMock()
    fake_flow.run_local_server.return_value = MagicMock(refresh_token="rt-x")
    with (
        patch(
            "cosinabox.cli.auth_google.InstalledAppFlow.from_client_config",
            return_value=fake_flow,
        ),
        patch("cosinabox.cli.auth_google._consented_email", return_value=None),
        pytest.raises(AccountUnverifiableError),
    ):
        mint_refresh_token(
            client_id="cid", client_secret="sec", expected_email="rovik@example.com"
        )
```

Add `import pytest` at the top of the file if not already present.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/.worktrees/cosinabox/feat-auth-refresh
pytest tests/unit/test_cli_auth_google.py -v
```

Expected: 4 new tests fail with `ImportError: cannot import name 'mint_refresh_token'` (and `AccountMismatchError`, `AccountUnverifiableError`). Existing 5 tests still pass.

- [ ] **Step 3: Implement the helper** in `src/cosinabox/cli/auth_google.py`

Replace the body of `auth_google_cmd` so the CLI command becomes a thin wrapper. Add two exception types and one helper. Final shape of the file:

```python
"""`cosinabox auth google` — OAuth flow to obtain Google refresh token."""

from __future__ import annotations

import os
from typing import Any

import click

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    InstalledAppFlow = None

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]


class AccountMismatchError(Exception):
    """Consent completed with a different Google account than --account requested."""


class AccountUnverifiableError(Exception):
    """Consent succeeded but the consented email could not be looked up."""


def _consented_email(creds: Any) -> str | None:
    """Return the email of the Google account that completed consent.

    Returns None on any failure — caller treats as "couldn't verify".
    """
    try:
        from googleapiclient.discovery import build  # type: ignore[import-untyped]

        svc = build("oauth2", "v2", credentials=creds, cache_discovery=False)
        info = svc.userinfo().get().execute()
    except Exception:  # noqa: BLE001 — best-effort verification
        return None
    email = info.get("email") if isinstance(info, dict) else None
    return str(email) if email else None


def mint_refresh_token(
    *, client_id: str, client_secret: str, expected_email: str | None
) -> str:
    """Run the Google OAuth installed-app flow and return the refresh token.

    Shared by `cosinabox auth google` (CLI) and `cosinabox auth refresh`
    (orchestrator). Raises ``AccountMismatchError`` /
    ``AccountUnverifiableError`` instead of leaking a token for the wrong
    account when ``expected_email`` is provided.
    """
    if InstalledAppFlow is None:
        raise RuntimeError(
            "google-auth-oauthlib is not installed. Run: pip install google-auth-oauthlib"
        )

    scopes = list(_SCOPES)
    if expected_email is not None:
        scopes.extend(
            ["openid", "https://www.googleapis.com/auth/userinfo.email"]
        )

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=scopes)
    creds = flow.run_local_server(port=0)

    if expected_email is not None:
        consented = _consented_email(creds)
        if consented is None:
            raise AccountUnverifiableError(
                "Could not verify which account completed consent — refusing "
                f"to print a refresh token for --account {expected_email}. "
                "Re-run without --account to skip the check."
            )
        if consented.lower() != expected_email.lower():
            raise AccountMismatchError(
                f"Consent screen completed with {consented}, not "
                f"{expected_email}. Refusing to print the token — it would "
                "be for the wrong inbox. Sign out of the wrong account in "
                "your browser (or use a private window) and re-run."
            )

    return str(creds.refresh_token)


@click.group("auth")
def auth_cmd() -> None:
    """Authentication helpers."""


@auth_cmd.command("google")
@click.option(
    "--account",
    "expected_email",
    default=None,
    help=(
        "Email of the Google account this token is FOR. If the consent "
        "screen completes with a different account, the flow refuses to "
        "print the token. Use this for multi-account setups so a stray "
        "browser session can't silently mint a token for the wrong inbox."
    ),
)
def auth_google_cmd(expected_email: str | None) -> None:
    """Run Google OAuth flow and print the refresh token."""
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise click.ClickException(
            "GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be set."
        )

    try:
        token = mint_refresh_token(
            client_id=client_id,
            client_secret=client_secret,
            expected_email=expected_email,
        )
    except (AccountMismatchError, AccountUnverifiableError) as e:
        raise click.ClickException(str(e)) from e
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e

    click.echo(f"Refresh token: {token}")
```

- [ ] **Step 4: Run all `auth_google` tests to verify green**

```bash
pytest tests/unit/test_cli_auth_google.py -v
```

Expected: 9 tests pass (5 existing + 4 new).

- [ ] **Step 5: Run the full unit suite to catch regressions**

```bash
pytest tests/unit/ -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/cosinabox/cli/auth_google.py tests/unit/test_cli_auth_google.py
git commit -m "refactor(cli): extract mint_refresh_token helper from auth_google

Prep for auth refresh orchestrator (Plan: 2026-05-06-oauth-auth-refresh, M2).
Helper returns the refresh token directly, raises typed exceptions on
account mismatch/unverifiable instead of click.ClickException, so the
new orchestrator can catch them programmatically."
```

**Estimate:** 30 min.

---

## M3 — Thin Railway adapter (`cli/_railway.py`)

**Why:** All Railway-specific subprocess calls live in one module so (a) tests can mock one boundary instead of `subprocess.run` everywhere, (b) when AWS/Fly land we add a sibling module without touching `auth_refresh.py`. Surface kept minimal — exactly the operations Initiative A needs.

**Files:**
- Create: `src/cosinabox/cli/_railway.py`
- Create: `tests/unit/test_cli_railway_adapter.py`

### Steps

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_cli_railway_adapter.py`

```python
"""Unit tests for the thin Railway CLI adapter (cli/_railway.py).

All `subprocess` invocations are mocked. These tests do not touch the
network or the user's Railway state.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from cosinabox.cli import _railway


def _make_completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_cli_available_true_when_on_path() -> None:
    with patch("cosinabox.cli._railway.shutil.which", return_value="/usr/local/bin/railway"):
        assert _railway.cli_available() is True


def test_cli_available_false_when_missing() -> None:
    with patch("cosinabox.cli._railway.shutil.which", return_value=None):
        assert _railway.cli_available() is False


def test_whoami_returns_user_string() -> None:
    with patch(
        "cosinabox.cli._railway.subprocess.run",
        return_value=_make_completed(stdout="rovik@example.com\n"),
    ):
        assert _railway.whoami() == "rovik@example.com"


def test_whoami_raises_railway_error_on_nonzero() -> None:
    with (
        patch(
            "cosinabox.cli._railway.subprocess.run",
            return_value=_make_completed(returncode=1, stdout="not logged in"),
        ),
        pytest.raises(_railway.RailwayError) as exc,
    ):
        _railway.whoami()
    assert "railway login" in str(exc.value).lower()


def test_status_returns_parsed_dict() -> None:
    payload = {"projectId": "p1", "projectName": "rovik-keevs", "serviceName": "bot"}
    with patch(
        "cosinabox.cli._railway.subprocess.run",
        return_value=_make_completed(stdout=json.dumps(payload)),
    ):
        s = _railway.status()
    assert s["projectName"] == "rovik-keevs"
    assert s["serviceName"] == "bot"


def test_status_raises_when_no_service_linked() -> None:
    # `railway status --json` exits non-zero in some "no service" states; in
    # others it returns a payload missing the service field. Cover both.
    with (
        patch(
            "cosinabox.cli._railway.subprocess.run",
            return_value=_make_completed(returncode=1, stdout=""),
        ),
        pytest.raises(_railway.RailwayError) as exc,
    ):
        _railway.status()
    assert "railway link" in str(exc.value).lower()


def test_get_variable_returns_value() -> None:
    payload = {"GOOGLE_OAUTH_CLIENT_ID": "cid-123", "OTHER": "x"}
    with patch(
        "cosinabox.cli._railway.subprocess.run",
        return_value=_make_completed(stdout=json.dumps(payload)),
    ):
        assert _railway.get_variable("GOOGLE_OAUTH_CLIENT_ID") == "cid-123"


def test_get_variable_returns_none_when_absent() -> None:
    payload = {"OTHER": "x"}
    with patch(
        "cosinabox.cli._railway.subprocess.run",
        return_value=_make_completed(stdout=json.dumps(payload)),
    ):
        assert _railway.get_variable("MISSING") is None


def test_set_variable_passes_kv_to_cli() -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = list(args)
        return _make_completed()

    with patch("cosinabox.cli._railway.subprocess.run", side_effect=fake_run):
        _railway.set_variable("GOOGLE_OAUTH_REFRESH_TOKEN_1", "rt-new")

    assert "variables" in captured["args"]
    # The CLI form is `railway variables --set "K=V"`. Either flag style is
    # acceptable as long as the K=V pair appears intact in the command.
    joined = " ".join(captured["args"])
    assert "GOOGLE_OAUTH_REFRESH_TOKEN_1=rt-new" in joined


def test_set_variable_raises_on_failure() -> None:
    with (
        patch(
            "cosinabox.cli._railway.subprocess.run",
            return_value=_make_completed(returncode=1, stdout="permission denied"),
        ),
        pytest.raises(_railway.RailwayError),
    ):
        _railway.set_variable("X", "y")


def test_redeploy_invokes_up() -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = list(args)
        return _make_completed(stdout="building...")

    with patch("cosinabox.cli._railway.subprocess.run", side_effect=fake_run):
        _railway.redeploy()

    # Either `railway redeploy` or `railway up --ci` is acceptable; the impl
    # picks one. Test that *some* deploy verb is invoked.
    assert any(verb in captured["args"] for verb in ("redeploy", "up"))


def test_deployment_succeeded_polls_until_success() -> None:
    """Polls `railway status --json` until deployment reaches SUCCESS."""
    payloads = iter(
        [
            json.dumps({"latestDeployment": {"status": "BUILDING"}}),
            json.dumps({"latestDeployment": {"status": "DEPLOYING"}}),
            json.dumps({"latestDeployment": {"status": "SUCCESS"}}),
        ]
    )
    with (
        patch(
            "cosinabox.cli._railway.subprocess.run",
            side_effect=lambda *_a, **_kw: _make_completed(stdout=next(payloads)),
        ),
        patch("cosinabox.cli._railway.time.sleep") as fake_sleep,
    ):
        ok = _railway.wait_for_deployment(timeout_seconds=60, poll_interval=2)
    assert ok is True
    assert fake_sleep.called


def test_deployment_succeeded_returns_false_on_failure_status() -> None:
    payloads = iter(
        [
            json.dumps({"latestDeployment": {"status": "BUILDING"}}),
            json.dumps({"latestDeployment": {"status": "FAILED"}}),
        ]
    )
    with (
        patch(
            "cosinabox.cli._railway.subprocess.run",
            side_effect=lambda *_a, **_kw: _make_completed(stdout=next(payloads)),
        ),
        patch("cosinabox.cli._railway.time.sleep"),
    ):
        ok = _railway.wait_for_deployment(timeout_seconds=60, poll_interval=2)
    assert ok is False


def test_deployment_succeeded_returns_false_on_timeout() -> None:
    with (
        patch(
            "cosinabox.cli._railway.subprocess.run",
            return_value=_make_completed(stdout=json.dumps({"latestDeployment": {"status": "BUILDING"}})),
        ),
        patch("cosinabox.cli._railway.time.sleep"),
        patch("cosinabox.cli._railway.time.monotonic", side_effect=[0, 0, 100, 200]),
    ):
        ok = _railway.wait_for_deployment(timeout_seconds=60, poll_interval=2)
    assert ok is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_cli_railway_adapter.py -v
```

Expected: all fail with `ModuleNotFoundError: cosinabox.cli._railway`.

- [ ] **Step 3: Implement the adapter** in `src/cosinabox/cli/_railway.py`

```python
"""Thin Railway CLI subprocess adapter — used by `cosinabox auth refresh`.

This module is intentionally minimal. It wraps exactly the Railway CLI
operations Initiative A needs (whoami, status, variables get/set,
redeploy, wait-for-deploy). Each function shells out to the user's
locally-installed `railway` binary; nothing here speaks the Railway HTTP
API directly.

When AWS / Fly support lands, the right move is to add a sibling
``_aws.py`` / ``_fly.py`` and a tiny dispatcher in ``auth_refresh.py``.
Do not generalise this module ahead of that need — the abstraction
shape is unknown until we have a second target to learn from.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import Any


class RailwayError(RuntimeError):
    """Wrapped failure from a Railway CLI subprocess call.

    Each error message includes the exact CLI command the user can run
    to fix the underlying problem (login, link, etc.).
    """


def cli_available() -> bool:
    """Return True if the `railway` binary is on PATH."""
    return shutil.which("railway") is not None


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
    )


def whoami() -> str:
    """Return the email of the logged-in Railway account.

    Raises ``RailwayError`` with a fix hint if the CLI is not logged in.
    """
    res = _run(["railway", "whoami"])
    if res.returncode != 0:
        raise RailwayError(
            "Not logged in to Railway. Run: railway login"
        )
    return res.stdout.strip()


def status() -> dict[str, Any]:
    """Return the linked project/service status as a dict.

    Raises ``RailwayError`` with a fix hint if no service is linked
    in the current directory.
    """
    res = _run(["railway", "status", "--json"])
    if res.returncode != 0 or not res.stdout.strip():
        raise RailwayError(
            "No Railway service linked in this directory. Run: railway link"
        )
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError as e:
        raise RailwayError(
            f"Could not parse `railway status --json` output: {e}"
        ) from e
    if not isinstance(data, dict):
        raise RailwayError(
            "Unexpected `railway status --json` payload shape."
        )
    return data


def get_variable(name: str) -> str | None:
    """Return the value of a Railway service variable, or None if absent."""
    res = _run(["railway", "variables", "--json"])
    if res.returncode != 0:
        raise RailwayError(
            "Could not read Railway variables. "
            "Check `railway status` and re-run."
        )
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError as e:
        raise RailwayError(
            f"Could not parse `railway variables --json`: {e}"
        ) from e
    if not isinstance(data, dict):
        return None
    val = data.get(name)
    return str(val) if val is not None else None


def set_variable(name: str, value: str) -> None:
    """Set a Railway service variable."""
    res = _run(["railway", "variables", "--set", f"{name}={value}"])
    if res.returncode != 0:
        raise RailwayError(
            f"Could not set {name} on Railway. CLI output: {res.stdout or res.stderr}"
        )


def redeploy() -> None:
    """Trigger a redeploy on the linked Railway service.

    Uses `railway redeploy` (newer CLIs) which redeploys the most recent
    deployment. The call returns once the redeploy has been *queued* —
    it does not wait for the deployment to succeed. Use
    ``wait_for_deployment`` for that.
    """
    res = _run(["railway", "redeploy", "--yes"])
    if res.returncode != 0:
        raise RailwayError(
            f"Could not trigger redeploy. CLI output: {res.stdout or res.stderr}"
        )


def wait_for_deployment(
    *, timeout_seconds: int = 300, poll_interval: int = 5
) -> bool:
    """Poll `railway status` until the latest deployment reaches a terminal state.

    Returns True on SUCCESS, False on FAILED/CRASHED/timeout. Does not
    raise — callers print a friendly message based on the boolean.
    """
    start = time.monotonic()
    while time.monotonic() - start < timeout_seconds:
        try:
            data = status()
        except RailwayError:
            return False
        latest = data.get("latestDeployment") or {}
        st = str(latest.get("status", "")).upper()
        if st == "SUCCESS":
            return True
        if st in ("FAILED", "CRASHED", "REMOVED"):
            return False
        time.sleep(poll_interval)
    return False
```

- [ ] **Step 4: Run tests to verify green**

```bash
pytest tests/unit/test_cli_railway_adapter.py -v
```

Expected: all pass.

- [ ] **Step 5: Run lint + types**

```bash
ruff check src/cosinabox/cli/_railway.py tests/unit/test_cli_railway_adapter.py
mypy src/cosinabox/cli/_railway.py
```

Expected: no warnings.

- [ ] **Step 6: Commit**

```bash
git add src/cosinabox/cli/_railway.py tests/unit/test_cli_railway_adapter.py
git commit -m "feat(cli): thin Railway CLI adapter for auth refresh

Plan: 2026-05-06-oauth-auth-refresh, M3.
Wraps the railway CLI subprocess calls that auth refresh needs:
whoami, status, variables get/set, redeploy, wait_for_deployment.
Minimal surface so AWS/Fly can ship sibling modules later without
needing to refactor a premature abstraction."
```

**Estimate:** 1 hr.

---

## M4 — `auth refresh` command: happy path (single-account)

**Why:** Smallest end-to-end slice. Single-account user runs `cosinabox auth refresh`, picker is skipped, creds pulled from Railway, mint helper runs, token written back, redeploy fires, deployment confirmed. All Railway calls and the consent flow are mocked.

**Files:**
- Create: `src/cosinabox/cli/auth_refresh.py`
- Modify: `src/cosinabox/cli/main.py` (register the new command on the `auth` group)
- Create: `tests/unit/test_cli_auth_refresh.py`

### Steps

- [ ] **Step 1: Write the failing test** in `tests/unit/test_cli_auth_refresh.py`

```python
"""Tests for `cosinabox auth refresh`.

All Railway CLI calls and the OAuth consent flow are mocked. These
tests verify orchestration logic, not the real Railway CLI or Google
OAuth (those are tested independently in their own modules).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from cosinabox.cli.main import cli


def _write_integrations(tmp_path: Path, accounts: list[dict[str, str]]) -> Path:
    cfg = {
        "schema_version": 1,
        "integrations": {"google": {"enabled": True, "accounts": accounts}},
    }
    (tmp_path / "integrations.yaml").write_text(yaml.safe_dump(cfg))
    return tmp_path


def test_auth_refresh_happy_path_single_account(tmp_path: Path) -> None:
    """Single-account user → no picker → mint → set _1 → redeploy → SUCCESS."""
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])

    set_calls: list[tuple[str, str]] = []

    with (
        patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=True),
        patch(
            "cosinabox.cli.auth_refresh._railway.whoami",
            return_value="rovik@example.com",
        ),
        patch(
            "cosinabox.cli.auth_refresh._railway.status",
            return_value={
                "projectName": "rovik-keevs",
                "serviceName": "bot",
                "latestDeployment": {"status": "SUCCESS"},
            },
        ),
        patch(
            "cosinabox.cli.auth_refresh._railway.get_variable",
            side_effect=lambda name: {
                "GOOGLE_OAUTH_CLIENT_ID": "cid-from-railway",
                "GOOGLE_OAUTH_CLIENT_SECRET": "sec-from-railway",
            }.get(name),
        ),
        patch(
            "cosinabox.cli.auth_refresh._railway.set_variable",
            side_effect=lambda n, v: set_calls.append((n, v)),
        ),
        patch("cosinabox.cli.auth_refresh._railway.redeploy") as redeploy,
        patch(
            "cosinabox.cli.auth_refresh._railway.wait_for_deployment",
            return_value=True,
        ),
        patch(
            "cosinabox.cli.auth_refresh.mint_refresh_token",
            return_value="rt-fresh-from-google",
        ),
    ):
        result = CliRunner().invoke(
            cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes"]
        )

    assert result.exit_code == 0, result.output
    # Single-account path: no picker shown.
    assert "Pick" not in result.output and "Choose" not in result.output
    # The chosen account is announced.
    assert "rovik@example.com" in result.output
    # The token was written to slot _1.
    assert ("GOOGLE_OAUTH_REFRESH_TOKEN_1", "rt-fresh-from-google") in set_calls
    # Redeploy fired and we reported success.
    redeploy.assert_called_once()
    assert "redeploy" in result.output.lower()
    assert "success" in result.output.lower() or "auth_health" in result.output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_cli_auth_refresh.py::test_auth_refresh_happy_path_single_account -v
```

Expected: fails with `ModuleNotFoundError: cosinabox.cli.auth_refresh`.

- [ ] **Step 3: Implement the orchestrator** in `src/cosinabox/cli/auth_refresh.py`

```python
"""`cosinabox auth refresh` — guided Google OAuth re-auth orchestrator.

Collapses the 10-step manual re-auth flow (Google Cloud Console hunt →
pull creds from Railway → run consent → write token back → redeploy
→ verify) into one command.

Initiative A of the OAuth UX rework spec (2026-05-06).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from cosinabox.cli import _railway
from cosinabox.cli.auth_google import (
    AccountMismatchError,
    AccountUnverifiableError,
    mint_refresh_token,
)


def _load_google_accounts(config_dir: Path) -> list[dict[str, Any]]:
    """Return the configured Google accounts list from integrations.yaml."""
    from cosinabox.app.config import load_integrations

    integrations = load_integrations(config_dir)
    google = integrations.get("google", {})
    if not isinstance(google, dict) or not google.get("enabled"):
        raise click.ClickException(
            "Google integration is not enabled in integrations.yaml. "
            "Nothing to refresh."
        )
    accounts = google.get("accounts") or []
    if not isinstance(accounts, list) or not accounts:
        raise click.ClickException(
            "No Google accounts configured in integrations.yaml. "
            "Add an account under integrations.google.accounts first."
        )
    out: list[dict[str, Any]] = []
    for a in accounts:
        if isinstance(a, dict) and isinstance(a.get("email"), str):
            out.append(a)
    if not out:
        raise click.ClickException(
            "integrations.yaml has google.accounts but no entries with an "
            "`email` field. Each account needs `email: <address>`."
        )
    return out


def _pick_account(
    accounts: list[dict[str, Any]], requested: str | None
) -> tuple[int, dict[str, Any]]:
    """Return (1-based index, account dict).

    - If ``requested`` matches an account email, use it.
    - If exactly one account configured, auto-select with a notice.
    - Else prompt the user with a numbered picker.
    """
    if requested is not None:
        for i, a in enumerate(accounts, start=1):
            if str(a["email"]).lower() == requested.lower():
                return i, a
        raise click.ClickException(
            f"--account {requested} does not match any account in "
            f"integrations.yaml. Configured: "
            f"{', '.join(a['email'] for a in accounts)}"
        )

    if len(accounts) == 1:
        click.echo(f"Refreshing token for {accounts[0]['email']}...")
        return 1, accounts[0]

    click.echo("Multiple Google accounts configured. Pick one:")
    for i, a in enumerate(accounts, start=1):
        click.echo(f"  {i}. {a['email']}")
    choice = click.prompt(
        "Number", type=click.IntRange(1, len(accounts))
    )
    return choice, accounts[choice - 1]


def _check_railway_environment(yes: bool) -> dict[str, Any]:
    """Verify Railway CLI is installed, logged in, and a service is linked.

    Prints the detected project/service and asks for confirmation
    unless ``--yes`` was passed.
    """
    if not _railway.cli_available():
        raise click.ClickException(
            "Railway CLI not installed. Install: "
            "https://docs.railway.com/guides/cli"
        )

    try:
        _railway.whoami()
    except _railway.RailwayError as e:
        raise click.ClickException(str(e)) from e

    try:
        st = _railway.status()
    except _railway.RailwayError as e:
        raise click.ClickException(str(e)) from e

    project = st.get("projectName") or st.get("project") or "(unknown project)"
    service = st.get("serviceName") or st.get("service") or "(unknown service)"
    click.echo(f"Detected Railway: project={project} service={service}")
    if not yes:
        if not click.confirm("Continue?", default=False):
            raise click.ClickException("Aborted by user.")
    return st


def _resolve_token_var_name(railway_status: dict[str, Any], slot: int) -> str:
    """Return the env-var name to write the new refresh token to.

    Defaults to ``GOOGLE_OAUTH_REFRESH_TOKEN_<slot>``. If the deployment
    only has the legacy unsuffixed ``GOOGLE_OAUTH_REFRESH_TOKEN`` var,
    we still write to ``_<slot>`` (the new convention) and warn the user.
    """
    new_name = f"GOOGLE_OAUTH_REFRESH_TOKEN_{slot}"
    has_new = _railway.get_variable(new_name) is not None
    has_legacy = (
        slot == 1 and _railway.get_variable("GOOGLE_OAUTH_REFRESH_TOKEN") is not None
    )
    if not has_new and has_legacy:
        click.echo(
            "Note: your deploy uses the legacy GOOGLE_OAUTH_REFRESH_TOKEN "
            "(no number). Writing the new token to "
            f"{new_name} (the current convention). You can delete the "
            "legacy variable after the next briefing succeeds."
        )
    return new_name


@click.command("refresh")
@click.option(
    "--account",
    "requested",
    default=None,
    help="Email of the Google account to refresh. Skips the picker.",
)
@click.option(
    "--yes",
    is_flag=True,
    default=False,
    help="Skip the project/service confirmation prompt.",
)
@click.option(
    "--no-wait",
    is_flag=True,
    default=False,
    help="Don't wait for the redeploy to finish before returning.",
)
@click.pass_context
def auth_refresh_cmd(
    ctx: click.Context, requested: str | None, yes: bool, no_wait: bool
) -> None:
    """Run the full Google OAuth re-auth flow against the linked deploy.

    Reads integrations.yaml, picks an account (or auto-selects when one
    is configured), pulls OAuth client creds from Railway, runs consent
    in the browser, writes the new refresh token back to Railway, and
    triggers a redeploy. Use after `auth_health` alerts you to a dead
    token.
    """
    config_dir: Path = ctx.obj["config_dir"]

    accounts = _load_google_accounts(config_dir)
    slot, picked = _pick_account(accounts, requested)
    picked_email = str(picked["email"])

    rail_status = _check_railway_environment(yes)

    client_id = _railway.get_variable("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = _railway.get_variable("GOOGLE_OAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise click.ClickException(
            "GOOGLE_OAUTH_CLIENT_ID or GOOGLE_OAUTH_CLIENT_SECRET is not set "
            "on the linked Railway service. Set both before running "
            "`cosinabox auth refresh`."
        )

    click.echo("Opening Google consent screen in your browser...")
    try:
        token = mint_refresh_token(
            client_id=client_id,
            client_secret=client_secret,
            expected_email=picked_email,
        )
    except AccountMismatchError as e:
        raise click.ClickException(str(e)) from e
    except AccountUnverifiableError as e:
        raise click.ClickException(str(e)) from e

    var_name = _resolve_token_var_name(rail_status, slot)
    click.echo(f"Writing new refresh token to {var_name}...")
    try:
        _railway.set_variable(var_name, token)
    except _railway.RailwayError as e:
        raise click.ClickException(str(e)) from e

    click.echo("Triggering redeploy...")
    try:
        _railway.redeploy()
    except _railway.RailwayError as e:
        raise click.ClickException(str(e)) from e

    if no_wait:
        click.echo(
            "Redeploy queued. Check `railway logs` and watch the next "
            "auth_health Telegram alert (≤15 min) to confirm the new "
            "token works."
        )
        return

    click.echo("Waiting for the redeploy to complete (timeout 5 min)...")
    if _railway.wait_for_deployment(timeout_seconds=300, poll_interval=5):
        click.echo(
            f"Redeploy succeeded. The next auth_health tick (≤15 min) will "
            f"confirm {picked_email} works. You'll get a Telegram alert if "
            "it doesn't."
        )
    else:
        raise click.ClickException(
            "Redeploy did not reach SUCCESS within 5 minutes. The token "
            "was written to Railway, but the deploy may have failed. Run "
            "`railway logs` to inspect."
        )
```

- [ ] **Step 4: Register the command** — edit `src/cosinabox/cli/main.py`. Add this import alongside the other CLI imports:

```python
from cosinabox.cli.auth_google import auth_cmd
from cosinabox.cli.auth_refresh import auth_refresh_cmd
```

And after `cli.add_command(auth_cmd)`, add:

```python
auth_cmd.add_command(auth_refresh_cmd)
```

- [ ] **Step 5: Run the test to verify green**

```bash
pytest tests/unit/test_cli_auth_refresh.py::test_auth_refresh_happy_path_single_account -v
```

Expected: pass.

- [ ] **Step 6: Run the full unit suite**

```bash
pytest tests/unit/ -q
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/cosinabox/cli/auth_refresh.py src/cosinabox/cli/main.py tests/unit/test_cli_auth_refresh.py
git commit -m "feat(cli): auth refresh orchestrator (single-account happy path)

Plan: 2026-05-06-oauth-auth-refresh, M4.
One command that pulls OAuth client creds from Railway, runs consent,
writes the new refresh token back, and redeploys. Single-account users
skip the picker. Multi-account picker + failure-mode coverage land in
M5/M6."
```

**Estimate:** 1 hr.

---

## M5 — Multi-account picker and `--account` flag

**Why:** Cover the two non-default selection paths: explicit `--account <email>` and the interactive numbered picker. Also covers slot calculation for the second/third account.

**Files:**
- Modify: `tests/unit/test_cli_auth_refresh.py`

(All implementation should already exist from M4 — these tests verify it.)

### Steps

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_cli_auth_refresh.py`)

```python
def _patch_happy_path_railway(token_for_email: dict[str, str]) -> Any:
    """Helper that returns a context manager bundling all Railway/mint mocks.

    Used by tests that vary picker behaviour but otherwise want the happy
    path. Each test that uses this passes a dict mapping the picked email
    → the refresh token mint should return.
    """
    from contextlib import ExitStack

    set_calls: list[tuple[str, str]] = []

    def enter() -> tuple[ExitStack, list[tuple[str, str]]]:
        stack = ExitStack()
        stack.enter_context(
            patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=True)
        )
        stack.enter_context(
            patch("cosinabox.cli.auth_refresh._railway.whoami", return_value="x")
        )
        stack.enter_context(
            patch(
                "cosinabox.cli.auth_refresh._railway.status",
                return_value={
                    "projectName": "rovik-keevs",
                    "serviceName": "bot",
                    "latestDeployment": {"status": "SUCCESS"},
                },
            )
        )
        stack.enter_context(
            patch(
                "cosinabox.cli.auth_refresh._railway.get_variable",
                side_effect=lambda n: {
                    "GOOGLE_OAUTH_CLIENT_ID": "cid",
                    "GOOGLE_OAUTH_CLIENT_SECRET": "sec",
                }.get(n),
            )
        )
        stack.enter_context(
            patch(
                "cosinabox.cli.auth_refresh._railway.set_variable",
                side_effect=lambda n, v: set_calls.append((n, v)),
            )
        )
        stack.enter_context(
            patch("cosinabox.cli.auth_refresh._railway.redeploy")
        )
        stack.enter_context(
            patch(
                "cosinabox.cli.auth_refresh._railway.wait_for_deployment",
                return_value=True,
            )
        )

        def fake_mint(*, client_id: str, client_secret: str, expected_email: str | None) -> str:
            assert expected_email is not None
            return token_for_email[expected_email]

        stack.enter_context(
            patch("cosinabox.cli.auth_refresh.mint_refresh_token", side_effect=fake_mint)
        )
        return stack, set_calls

    return enter


def test_auth_refresh_account_flag_selects_named_account(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(
        tmp_path,
        [{"email": "primary@example.com"}, {"email": "secondary@example.com"}],
    )
    enter = _patch_happy_path_railway(
        {"secondary@example.com": "rt-secondary"}
    )
    stack, set_calls = enter()
    with stack:
        result = CliRunner().invoke(
            cli,
            [
                "-C", str(cfg_dir),
                "auth", "refresh",
                "--account", "secondary@example.com",
                "--yes",
            ],
        )
    assert result.exit_code == 0, result.output
    # Slot 2 because secondary is accounts[1].
    assert ("GOOGLE_OAUTH_REFRESH_TOKEN_2", "rt-secondary") in set_calls


def test_auth_refresh_account_flag_unknown_email_errors(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(
        tmp_path, [{"email": "primary@example.com"}]
    )
    # No mocks needed past load_integrations — we should bail before
    # touching Railway.
    result = CliRunner().invoke(
        cli,
        [
            "-C", str(cfg_dir),
            "auth", "refresh",
            "--account", "stranger@example.com",
            "--yes",
        ],
    )
    assert result.exit_code != 0
    assert "stranger@example.com" in result.output
    assert "primary@example.com" in result.output  # configured ones listed


def test_auth_refresh_picker_writes_to_chosen_slot(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(
        tmp_path,
        [{"email": "primary@example.com"}, {"email": "secondary@example.com"}],
    )
    enter = _patch_happy_path_railway(
        {"secondary@example.com": "rt-picked"}
    )
    stack, set_calls = enter()
    with stack:
        # CliRunner's `input` feeds stdin to click.prompt.
        result = CliRunner().invoke(
            cli,
            ["-C", str(cfg_dir), "auth", "refresh", "--yes"],
            input="2\n",
        )
    assert result.exit_code == 0, result.output
    # Picker lines printed.
    assert "1. primary@example.com" in result.output
    assert "2. secondary@example.com" in result.output
    assert ("GOOGLE_OAUTH_REFRESH_TOKEN_2", "rt-picked") in set_calls


def test_auth_refresh_account_flag_is_case_insensitive(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(
        tmp_path, [{"email": "Mixed@Example.COM"}]
    )
    enter = _patch_happy_path_railway({"Mixed@Example.COM": "rt-case"})
    stack, set_calls = enter()
    with stack:
        result = CliRunner().invoke(
            cli,
            [
                "-C", str(cfg_dir),
                "auth", "refresh",
                "--account", "mixed@example.com",
                "--yes",
            ],
        )
    assert result.exit_code == 0, result.output
    assert ("GOOGLE_OAUTH_REFRESH_TOKEN_1", "rt-case") in set_calls
```

- [ ] **Step 2: Run the new tests**

```bash
pytest tests/unit/test_cli_auth_refresh.py -v -k "account_flag or picker or case_insensitive"
```

Expected: all four tests pass without modifying production code (M4's implementation already covers these paths). If any fail, fix the implementation, then re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_cli_auth_refresh.py
git commit -m "test(cli): cover --account flag and multi-account picker for auth refresh

Plan: 2026-05-06-oauth-auth-refresh, M5.
Verifies slot calculation matches accounts[i] ↔ REFRESH_TOKEN_<i+1>,
case-insensitive --account matching, and the unknown-email error path."
```

**Estimate:** 30 min.

---

## M6 — Failure-mode coverage (the six from the spec)

**Why:** The spec lists six concrete failures from the 2026-05-06 session. Each maps to a test here, and each test forces the orchestrator to surface a specific friendly error or alert. This is the test matrix for "did we actually solve the UX problem".

**Failure → test mapping:**

| # | Spec failure | Test name |
|---|---|---|
| 1 | `cosinabox.cli` not installed locally | `test_railway_cli_missing_friendly_error` (proxy: same "tooling not present" UX class) |
| 2 | Railway env var truncated | Mooted by automation — set via `set_variable`, no copy-paste. Document in plan, no test. |
| 3 | Wrong Google account in consent | `test_account_mismatch_surfaces_friendly_error` |
| 4 | Working-but-wrong token (silent corruption) | Same as #3 — `mint_refresh_token` raises before write. |
| 5 | Invisible `_REFRESH_TOKEN_N` numbering | `test_announces_chosen_slot_in_output` |
| 6 | Account-revoked silent until briefing | Out of scope — fixed by the runtime alert wiring already shipped in 0.1.5. Document in plan. |

Plus a few orchestrator-specific failure tests:

- `test_railway_not_logged_in_friendly_error`
- `test_railway_no_service_linked_friendly_error`
- `test_redeploy_fails_or_times_out`
- `test_legacy_unsuffixed_token_warning`
- `test_no_google_integration_errors`

**Files:**
- Modify: `tests/unit/test_cli_auth_refresh.py`

### Steps

- [ ] **Step 1: Write the failing tests** (append to `tests/unit/test_cli_auth_refresh.py`)

```python
def test_railway_cli_missing_friendly_error(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])
    with patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=False):
        result = CliRunner().invoke(
            cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes"]
        )
    assert result.exit_code != 0
    assert "railway cli" in result.output.lower()
    assert "install" in result.output.lower()


def test_railway_not_logged_in_friendly_error(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])
    from cosinabox.cli._railway import RailwayError

    with (
        patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=True),
        patch(
            "cosinabox.cli.auth_refresh._railway.whoami",
            side_effect=RailwayError("Not logged in to Railway. Run: railway login"),
        ),
    ):
        result = CliRunner().invoke(
            cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes"]
        )
    assert result.exit_code != 0
    assert "railway login" in result.output.lower()


def test_railway_no_service_linked_friendly_error(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])
    from cosinabox.cli._railway import RailwayError

    with (
        patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=True),
        patch("cosinabox.cli.auth_refresh._railway.whoami", return_value="x"),
        patch(
            "cosinabox.cli.auth_refresh._railway.status",
            side_effect=RailwayError(
                "No Railway service linked in this directory. Run: railway link"
            ),
        ),
    ):
        result = CliRunner().invoke(
            cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes"]
        )
    assert result.exit_code != 0
    assert "railway link" in result.output.lower()


def test_account_mismatch_surfaces_friendly_error(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(tmp_path, [{"email": "intended@example.com"}])
    from cosinabox.cli.auth_google import AccountMismatchError

    with (
        patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=True),
        patch("cosinabox.cli.auth_refresh._railway.whoami", return_value="x"),
        patch(
            "cosinabox.cli.auth_refresh._railway.status",
            return_value={"projectName": "p", "serviceName": "s"},
        ),
        patch(
            "cosinabox.cli.auth_refresh._railway.get_variable",
            side_effect=lambda n: {
                "GOOGLE_OAUTH_CLIENT_ID": "cid",
                "GOOGLE_OAUTH_CLIENT_SECRET": "sec",
            }.get(n),
        ),
        patch(
            "cosinabox.cli.auth_refresh.mint_refresh_token",
            side_effect=AccountMismatchError(
                "Consent screen completed with stranger@example.com, not "
                "intended@example.com. Refusing to print the token."
            ),
        ),
        patch(
            "cosinabox.cli.auth_refresh._railway.set_variable",
        ) as set_var,
        patch("cosinabox.cli.auth_refresh._railway.redeploy") as redeploy,
    ):
        result = CliRunner().invoke(
            cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes"]
        )
    assert result.exit_code != 0
    assert "stranger@example.com" in result.output
    assert "intended@example.com" in result.output
    # Critical: nothing is written to Railway and no redeploy happens.
    set_var.assert_not_called()
    redeploy.assert_not_called()


def test_announces_chosen_slot_in_output(tmp_path: Path) -> None:
    """Failure mode #5: the _N → email mapping must be visible to the user.

    The output should mention which env var slot the new token went into,
    so the user can map it to their Railway dashboard if they need to.
    """
    cfg_dir = _write_integrations(
        tmp_path,
        [{"email": "first@example.com"}, {"email": "second@example.com"}],
    )
    enter = _patch_happy_path_railway({"second@example.com": "rt-x"})
    stack, _set_calls = enter()
    with stack:
        result = CliRunner().invoke(
            cli,
            [
                "-C", str(cfg_dir),
                "auth", "refresh",
                "--account", "second@example.com",
                "--yes",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "GOOGLE_OAUTH_REFRESH_TOKEN_2" in result.output


def test_redeploy_timeout_returns_actionable_error(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])
    enter = _patch_happy_path_railway({"rovik@example.com": "rt-x"})
    stack, _ = enter()
    # Override only the wait_for_deployment patch from the helper to
    # simulate timeout/failure. Use ExitStack.enter_context to re-patch.
    import contextlib

    with stack:
        with contextlib.ExitStack() as inner:
            inner.enter_context(
                patch(
                    "cosinabox.cli.auth_refresh._railway.wait_for_deployment",
                    return_value=False,
                )
            )
            result = CliRunner().invoke(
                cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes"]
            )
    assert result.exit_code != 0
    assert "railway logs" in result.output.lower()


def test_no_wait_flag_skips_deployment_poll(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])
    enter = _patch_happy_path_railway({"rovik@example.com": "rt-x"})
    stack, _ = enter()
    with stack:
        with patch(
            "cosinabox.cli.auth_refresh._railway.wait_for_deployment"
        ) as wait:
            result = CliRunner().invoke(
                cli,
                ["-C", str(cfg_dir), "auth", "refresh", "--yes", "--no-wait"],
            )
    assert result.exit_code == 0, result.output
    wait.assert_not_called()
    assert "queued" in result.output.lower() or "auth_health" in result.output.lower()


def test_legacy_unsuffixed_token_emits_warning(tmp_path: Path) -> None:
    cfg_dir = _write_integrations(tmp_path, [{"email": "rovik@example.com"}])

    def fake_get(name: str) -> str | None:
        # Simulate a deploy that has the legacy unsuffixed var but no _1.
        return {
            "GOOGLE_OAUTH_CLIENT_ID": "cid",
            "GOOGLE_OAUTH_CLIENT_SECRET": "sec",
            "GOOGLE_OAUTH_REFRESH_TOKEN": "old-token",
        }.get(name)

    with (
        patch("cosinabox.cli.auth_refresh._railway.cli_available", return_value=True),
        patch("cosinabox.cli.auth_refresh._railway.whoami", return_value="x"),
        patch(
            "cosinabox.cli.auth_refresh._railway.status",
            return_value={
                "projectName": "p",
                "serviceName": "s",
                "latestDeployment": {"status": "SUCCESS"},
            },
        ),
        patch(
            "cosinabox.cli.auth_refresh._railway.get_variable",
            side_effect=fake_get,
        ),
        patch("cosinabox.cli.auth_refresh._railway.set_variable"),
        patch("cosinabox.cli.auth_refresh._railway.redeploy"),
        patch(
            "cosinabox.cli.auth_refresh._railway.wait_for_deployment",
            return_value=True,
        ),
        patch(
            "cosinabox.cli.auth_refresh.mint_refresh_token",
            return_value="rt-new",
        ),
    ):
        result = CliRunner().invoke(
            cli, ["-C", str(cfg_dir), "auth", "refresh", "--yes"]
        )
    assert result.exit_code == 0, result.output
    assert "legacy" in result.output.lower()
    assert "GOOGLE_OAUTH_REFRESH_TOKEN_1" in result.output


def test_no_google_integration_errors(tmp_path: Path) -> None:
    cfg = {"schema_version": 1, "integrations": {"google": {"enabled": False}}}
    (tmp_path / "integrations.yaml").write_text(yaml.safe_dump(cfg))
    result = CliRunner().invoke(
        cli, ["-C", str(tmp_path), "auth", "refresh", "--yes"]
    )
    assert result.exit_code != 0
    assert "not enabled" in result.output.lower() or "nothing to refresh" in result.output.lower()
```

- [ ] **Step 2: Run the new tests**

```bash
pytest tests/unit/test_cli_auth_refresh.py -v
```

Expected: any tests that fail point at gaps in M4's implementation (e.g., the legacy-token warning may not be wired correctly). Fix the orchestrator to make them green; do NOT relax the assertions.

- [ ] **Step 3: Run the full unit suite**

```bash
pytest tests/unit/ -q
```

Expected: all green.

- [ ] **Step 4: Run lint + types over everything we touched**

```bash
ruff check src/cosinabox/cli/ tests/unit/test_cli_auth_refresh.py tests/unit/test_cli_railway_adapter.py
mypy src/cosinabox/cli/auth_refresh.py src/cosinabox/cli/_railway.py
```

Expected: no warnings.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_cli_auth_refresh.py src/cosinabox/cli/auth_refresh.py
git commit -m "test(cli): cover six failure modes for auth refresh

Plan: 2026-05-06-oauth-auth-refresh, M6.
Each test maps to a concrete failure observed in the 2026-05-06 session
listed in spec docs/specs/2026-05-06-oauth-ux-rework.md. Includes
legacy-token warning, redeploy timeout, account-mismatch refusal."
```

**Estimate:** 1 hr.

---

## M7 — Discoverability: update template oauth-walkthrough + CLI help

**Why:** OSS-user perspective rule (CLAUDE.md "OSS-user perspective" #2): every capability must be discoverable. New users find OAuth via `docs/agent/oauth-walkthrough.md` in their user-repo. That doc currently teaches the manual ten-step flow. After this initiative ships, it should lead with `cosinabox auth refresh` and keep the manual flow as a "if automation isn't an option" fallback.

**Files:**
- Modify: `src/cosinabox/templates/user-repo/docs/agent/oauth-walkthrough.md`

### Steps

- [ ] **Step 1: Read the current template doc**

```bash
cat src/cosinabox/templates/user-repo/docs/agent/oauth-walkthrough.md
```

- [ ] **Step 2: Restructure the doc** — top of the file becomes a "If your token expired" section that runs `cosinabox auth refresh`. The existing first-time-setup section (Google Cloud Console steps) stays, because Initiative A doesn't help first-time users.

Add this section near the top, immediately after the H1:

```markdown
## Re-auth: token expired

If `auth_health` Telegrammed you that a Google token expired, you do **not** need to repeat the manual GCP-console steps below. Run:

\`\`\`bash
cosinabox auth refresh
\`\`\`

This pulls your OAuth client creds from Railway, runs consent in your browser, writes the new refresh token back to Railway, and redeploys. If you have multiple Google accounts, it'll ask which one. If exactly one, it auto-selects.

Use the manual flow below only when:
- you're setting up a brand-new CoS for the first time, or
- you're not deploying to Railway (AWS / Fly support is on the roadmap), or
- `cosinabox auth refresh` itself errors out.

---

## First-time setup (manual GCP console flow)
```

(Keep the existing first-time content under that new H2.)

- [ ] **Step 3: Run the template tests**

```bash
pytest tests/unit/ -k "template or scaffold or init" -v
```

Expected: green (we only changed Markdown content; tests verifying scaffold structure shouldn't care).

- [ ] **Step 4: Smoke-test that `cosinabox init` still scaffolds the doc**

```bash
rm -rf /tmp/cos-init-smoke && cosinabox init /tmp/cos-init-smoke
grep -q "cosinabox auth refresh" /tmp/cos-init-smoke/docs/agent/oauth-walkthrough.md && echo "OK"
```

Expected: prints `OK`.

- [ ] **Step 5: Commit**

```bash
git add src/cosinabox/templates/user-repo/docs/agent/oauth-walkthrough.md
git commit -m "docs(template): lead oauth-walkthrough with cosinabox auth refresh

Plan: 2026-05-06-oauth-auth-refresh, M7.
Re-auth path now runs in one CLI command instead of ten manual steps.
Manual flow stays as fallback for first-time setup and non-Railway
deploys. OSS-user discoverability: a returning user should never see
the manual ten-step list again."
```

**Estimate:** 30 min.

---

## M8 — Manual smoke test against the maintainer's deploy (rovik-keevs)

**Why:** All M2–M7 tests run against mocks. Before merging, run `cosinabox auth refresh` for real against the maintainer's `rovik-keevs` Railway deploy, on whichever account has the dead token (`auth_health` will tell us which). Capture the actual user-facing output, note any rough edges, file a follow-up issue if anything is awkward.

**Files:**
- None modified. This is verification.

### Steps

- [ ] **Step 1: Confirm a target account.** Check the maintainer's Telegram for the latest `auth_health` alert OR run:
  ```bash
  cd ~/.worktrees/cosinabox/feat-auth-refresh
  pip install -e ".[dev,google]"
  cd <maintainer's user-repo working dir>
  cosinabox doctor
  ```
  Pick the account that doctor flags (or `rovik@cantina.ai` if that's the standing dead one from the 2026-05-06 session).

- [ ] **Step 2: Run the new command for real.**
  ```bash
  cosinabox auth refresh --account <picked-email>
  ```

- [ ] **Step 3: Verify success end-to-end.**
  - Confirm the consent screen used the right Google account.
  - Confirm the redeploy succeeded.
  - Wait ≤15 min for an `auth_health` Telegram message — should be the recovery message ("Google auth restored for account #N"), not a failure.

- [ ] **Step 4: Note rough edges.** Anything awkward (slow polling, confusing message, missing edge case) → file a GitHub issue OR add to the plan's "Out of scope / follow-ups" section. Do NOT fix in this plan unless it's blocking.

- [ ] **Step 5: Record outcome in the retro draft** (`docs/retros/2026-05-XX-oauth-auth-refresh-retro.md` — created in M9).

**Estimate:** 30 min (assumes one account refresh; longer if a real bug surfaces).

---

## M9 — PR, merge, retro

**Files:**
- Create: `docs/retros/2026-05-XX-oauth-auth-refresh-retro.md` (use `docs/retros/RETRO_TEMPLATE.md` if it exists; otherwise inline a short retro).

### Steps

- [ ] **Step 1: Verify all tests + lint + types pass on the worktree**

```bash
cd ~/.worktrees/cosinabox/feat-auth-refresh
pytest tests/ -q
ruff check src tests
mypy src/cosinabox
```

Expected: all green.

- [ ] **Step 2: Push the branch**

```bash
git push -u origin feat/auth-refresh
```

- [ ] **Step 3: Open a PR with auto-merge**

```bash
gh pr create \
  --title "feat(cli): cosinabox auth refresh — one-command Google OAuth re-auth" \
  --body "$(cat <<'EOF'
## Summary
- One CLI command (`cosinabox auth refresh`) collapses the 10-step manual re-auth flow.
- Single-account: auto-selects. Multi-account: numbered picker, or `--account <email>`.
- Pulls OAuth client creds from Railway, runs consent, writes the new refresh token back, redeploys, polls deploy status.
- Thin Railway adapter (`cli/_railway.py`) is the seam where AWS/Fly siblings will land.

Initiative A of `docs/specs/2026-05-06-oauth-ux-rework.md`. Plan: `docs/plans/2026-05-06-oauth-auth-refresh.md`.

## Test plan
- [x] Unit tests: `pytest tests/unit/test_cli_auth_refresh.py tests/unit/test_cli_railway_adapter.py tests/unit/test_cli_auth_google.py`
- [x] Six spec failure modes covered explicitly (M6).
- [x] Manual smoke against rovik-keevs (M8). Outcome: see retro.
- [x] Lint + types clean.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"

gh pr merge --auto --squash --delete-branch
```

- [ ] **Step 4: Write the retro** at `docs/retros/2026-05-06-oauth-auth-refresh-retro.md`. Cover:
  1. What shipped vs what was planned.
  2. Estimate calibration: which milestones overshot 2x, why.
  3. What worked well (keep doing).
  4. What didn't (change next time).
  5. Any commitment violations.
  6. New lessons → memory notes.

- [ ] **Step 5: Commit the retro on `main` (after the PR merges)**

```bash
git -C /Users/rovikrobert/code/cosinabox checkout main
git -C /Users/rovikrobert/code/cosinabox pull
git -C /Users/rovikrobert/code/cosinabox add docs/retros/2026-05-06-oauth-auth-refresh-retro.md
git -C /Users/rovikrobert/code/cosinabox commit -m "docs(retro): 2026-05-06 oauth-auth-refresh"
git -C /Users/rovikrobert/code/cosinabox push
```

- [ ] **Step 6: Worktree cleanup**

```bash
git -C /Users/rovikrobert/code/cosinabox worktree remove ~/.worktrees/cosinabox/feat-auth-refresh
```

**Estimate:** 15 min.

---

## Out of scope / follow-ups (for future plans)

- **Initiative B** (`cosinabox doctor` actively probes refresh tokens) — separate plan after A lands.
- **Initiative C** (`/status` per-account auth + alert message enrichment) — separate plan after B lands.
- **Initiative D** (web-based OAuth flow served by the bot itself) — v0.2 territory.
- **AWS / Fly deploy targets** — sibling adapter modules; introduced when first non-Railway user surfaces.
- **Tail logs in-process** for full-loop verification — only if the deploy-status poll proves insufficient in practice.
- **Auto-cleanup of legacy `GOOGLE_OAUTH_REFRESH_TOKEN`** (no `_N`) — currently we warn; future could add a `--migrate-legacy` flag.
- **`auth_refresh` exposed as a Telegram command** (`/refresh-auth`) — convenient if the bot itself can hand back a magic link. Initiative D adjacent.
