"""Thin Railway CLI subprocess adapter — used by `cosinabox auth refresh`.

Wraps exactly the Railway CLI operations Initiative A needs (whoami,
status, variable get/set, redeploy). Each function shells out to the
user's locally-installed `railway` binary; nothing here speaks the
Railway HTTP API directly.

Verified against railway CLI 4.30.2 (2026-05-06).

When AWS / Fly support lands, the right move is to add a sibling
``_aws.py`` / ``_fly.py`` and a tiny dispatcher in ``auth_refresh.py``.
Do not generalise this module ahead of that need — the abstraction
shape is unknown until we have a second target to learn from.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any


class RailwayError(RuntimeError):
    """Wrapped failure from a Railway CLI subprocess call.

    Each error message includes the exact CLI command the user can run
    to fix the underlying problem (login, link, etc.). The adapter is
    careful to NEVER include captured CLI stdout/stderr in error
    messages: Railway can echo back the variable value on validation
    failure, and we don't want a refresh token leaking into a
    user-facing exception string.
    """


def cli_available() -> bool:
    """Return True if the `railway` binary is on PATH."""
    return shutil.which("railway") is not None


def _run(args: list[str], *, stdin_value: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
        input=stdin_value,
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

    Schema (railway 4.30.2):
        {
          "id": str, "name": <project>, "deletedAt": null,
          "workspace": {...},
          "environments": {"edges": [{"node": {"id", "name"}}]},
          "services":     {"edges": [{"node": {"id", "name"}}]},
        }

    Note: there is no top-level ``projectName`` / ``serviceName`` /
    ``latestDeployment`` field. Callers must navigate the schema
    described above.

    Raises ``RailwayError`` with a fix hint if no service is linked.
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
    """Return the value of a Railway service variable, or None if absent.

    Uses the legacy ``railway variables --json`` form (railway 4.x still
    accepts this; the canonical command is ``railway variable list``).
    """
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
    """Set a Railway service variable.

    Uses ``railway variable set <KEY> --stdin`` so the *value* is passed
    via subprocess stdin and never appears in argv. Argv is observable
    to other users on the system via ``ps -ef``; for refresh tokens this
    is a real disclosure surface, hence the stdin path.

    On failure, raises ``RailwayError`` with the variable name and exit
    code only — never the captured stdout/stderr, because Railway can
    echo the value back in validation errors.
    """
    res = _run(
        ["railway", "variable", "set", name, "--stdin"],
        stdin_value=value,
    )
    if res.returncode != 0:
        raise RailwayError(
            f"Could not set {name} on Railway (railway CLI exit {res.returncode}). "
            "Run `railway variable list` to confirm permissions, then retry."
        )


def redeploy() -> None:
    """Trigger a redeploy on the linked Railway service.

    Returns once the redeploy is *queued*; does not block on completion.
    Verification of the new state is the job of the next ``auth_health``
    tick on the deploy itself (see auth_refresh.auth_refresh_cmd output).

    The error message intentionally omits captured stdout/stderr to keep
    the variable-leak avoidance discipline consistent across this module.
    """
    res = _run(["railway", "redeploy", "--yes"])
    if res.returncode != 0:
        raise RailwayError(
            f"Could not trigger redeploy (railway CLI exit {res.returncode}). "
            "Run `railway logs` to inspect, then retry."
        )
