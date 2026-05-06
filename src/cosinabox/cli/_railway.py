"""Thin Railway CLI subprocess adapter — used by `cosinabox auth refresh`.

This module is intentionally minimal. It wraps exactly the Railway CLI
operations Initiative A needs (whoami, status, variables get/set,
redeploy, wait-for-deploy). Each function shells out to the user's
locally-installed `railway` binary; nothing here speaks the Railway
HTTP API directly.

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
        raise RailwayError("Not logged in to Railway. Run: railway login")
    return res.stdout.strip()


def status() -> dict[str, Any]:
    """Return the linked project/service status as a dict.

    Raises ``RailwayError`` with a fix hint if no service is linked
    in the current directory.
    """
    res = _run(["railway", "status", "--json"])
    if res.returncode != 0 or not res.stdout.strip():
        raise RailwayError("No Railway service linked in this directory. Run: railway link")
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError as e:
        raise RailwayError(f"Could not parse `railway status --json` output: {e}") from e
    if not isinstance(data, dict):
        raise RailwayError("Unexpected `railway status --json` payload shape.")
    return data


def get_variable(name: str) -> str | None:
    """Return the value of a Railway service variable, or None if absent."""
    res = _run(["railway", "variables", "--json"])
    if res.returncode != 0:
        raise RailwayError("Could not read Railway variables. Check `railway status` and re-run.")
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError as e:
        raise RailwayError(f"Could not parse `railway variables --json`: {e}") from e
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
        raise RailwayError(f"Could not trigger redeploy. CLI output: {res.stdout or res.stderr}")


def wait_for_deployment(*, timeout_seconds: int = 300, poll_interval: int = 5) -> bool:
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
