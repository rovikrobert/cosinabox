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
            "Google integration is not enabled in integrations.yaml. Nothing to refresh."
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
    choice = click.prompt("Number", type=click.IntRange(1, len(accounts)))
    return choice, accounts[choice - 1]


def _check_railway_environment(yes: bool) -> dict[str, Any]:
    """Verify Railway CLI is installed, logged in, and a service is linked.

    Prints the detected project/service and asks for confirmation
    unless ``--yes`` was passed.
    """
    if not _railway.cli_available():
        raise click.ClickException(
            "Railway CLI not installed. Install: https://docs.railway.com/guides/cli"
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
    if not yes and not click.confirm("Continue?", default=False):
        raise click.ClickException("Aborted by user.")
    return st


def _resolve_token_var_name(slot: int) -> str:
    """Return the env-var name to write the new refresh token to.

    Defaults to ``GOOGLE_OAUTH_REFRESH_TOKEN_<slot>``. If the deployment
    only has the legacy unsuffixed ``GOOGLE_OAUTH_REFRESH_TOKEN`` var
    (and only for slot 1), surface a one-time warning explaining the
    transition.
    """
    new_name = f"GOOGLE_OAUTH_REFRESH_TOKEN_{slot}"
    has_new = _railway.get_variable(new_name) is not None
    has_legacy = slot == 1 and _railway.get_variable("GOOGLE_OAUTH_REFRESH_TOKEN") is not None
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
def auth_refresh_cmd(ctx: click.Context, requested: str | None, yes: bool, no_wait: bool) -> None:
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

    _check_railway_environment(yes)

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

    var_name = _resolve_token_var_name(slot)
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
