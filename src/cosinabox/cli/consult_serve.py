"""``cosinabox consult-serve`` — expose the CoS over MCP.

Defaults to **stdio** (same-machine only, no auth — the parent process is
trusted). HTTP transport requires ``CONSULT_API_KEY`` in env; the factory
is called with ``require_auth=True`` so Bearer authentication is
non-negotiable on the wire.

The ``mcp`` SDK is an optional extra (CLAUDE.md engine rule 5). When the
extra is missing, ``cosinabox.consult.build_consult_server`` is ``None``
(set by ``cosinabox/consult/__init__.py``). This command detects that case
and exits 1 with install instructions rather than raising ``TypeError``.
"""

from __future__ import annotations

import os
from pathlib import Path

import click

# Imported at module scope so tests can monkeypatch this attribute to
# ``None`` to simulate "mcp extra not installed". If we did
# ``from cosinabox.consult import build_consult_server`` inside the
# command, the monkeypatch wouldn't take effect — the patched name on the
# consult package is imported into this module's namespace once.
from cosinabox.consult import build_consult_server

_API_KEY_REQUIRED_MSG = (
    "error: CONSULT_API_KEY must be set for HTTP transport. "
    "Set it in .env or export it before running consult-serve."
)

_EXTRA_MISSING_MSG = (
    "error: consult-serve requires the 'consult' extra. "
    "Install it with: pip install 'cosinabox[consult]'"
)


def _parse_bind(raw: str) -> tuple[str, int]:
    """Split ``host:port`` into ``(host, port)``; port defaults to 8080.

    Raises ``ValueError`` on a malformed port so the CLI can surface a
    clean error rather than a stack trace.
    """
    host, sep, port_str = raw.partition(":")
    if not host:
        raise ValueError(f"invalid --bind value {raw!r}: host is empty")
    if not sep or not port_str:
        # Plain "host" with no colon => default port.
        return host, 8080
    try:
        port = int(port_str)
    except ValueError as exc:
        raise ValueError(
            f"invalid --bind value {raw!r}: port must be an integer, got {port_str!r}"
        ) from exc
    return host, port


@click.command("consult-serve")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "http"]),
    default="stdio",
    show_default=True,
    help="MCP transport. stdio is same-machine only; http exposes a network surface.",
)
@click.option(
    "--bind",
    default="127.0.0.1:8080",
    show_default=True,
    help=(
        "host:port (HTTP transport only). IPv4 only — "
        "IPv6 bracket syntax (e.g. '[::1]:8080') is not supported; "
        "bind to an IPv4 interface and front with a proxy if IPv6 is needed."
    ),
)
@click.pass_context
def consult_serve_cmd(ctx: click.Context, transport: str, bind: str) -> None:
    """Serve the CoS ``consult`` + ``brainstorm`` MCP tools.

    Default: stdio transport (spawned by an MCP client like Claude Code).
    HTTP transport requires ``CONSULT_API_KEY`` in the environment — the
    server rejects any request without a matching Bearer token.
    """
    if build_consult_server is None:
        # The ``mcp`` extra isn't installed — stay graceful per CLAUDE.md
        # rule 6 (graceful degradation).
        click.echo(_EXTRA_MISSING_MSG, err=True)
        ctx.exit(1)
        return  # pragma: no cover — ctx.exit raises

    config_dir: Path = ctx.obj["config_dir"]

    if transport == "stdio":
        server = build_consult_server(config_dir)
        server.run(transport="stdio")
        return

    # HTTP transport from here on.
    api_key = os.environ.get("CONSULT_API_KEY", "")
    if not api_key:
        click.echo(_API_KEY_REQUIRED_MSG, err=True)
        ctx.exit(1)
        return  # pragma: no cover — ctx.exit raises

    try:
        host, port = _parse_bind(bind)
    except ValueError as exc:
        click.echo(f"error: {exc}", err=True)
        ctx.exit(1)
        return  # pragma: no cover — ctx.exit raises

    server = build_consult_server(
        config_dir,
        api_key=api_key,
        require_auth=True,
    )
    # FastMCP reads host/port off ``server.settings`` when running the
    # streamable-http transport — see the M1 SDK vetting log.
    server.settings.host = host
    server.settings.port = port
    server.run(transport="streamable-http")
