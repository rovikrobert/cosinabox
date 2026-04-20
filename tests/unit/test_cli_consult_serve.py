"""Tests for the ``cosinabox consult-serve`` CLI subcommand.

Unit-level only — the MCP server factory is mocked so no real Anthropic /
memory / HTTP surface is spun up. The tests lock in the contract from M5 of
``docs/plans/2026-04-20-port-consult-mcp.md``:

- ``--transport`` and ``--bind`` are advertised in ``--help``.
- Default transport is ``stdio``; that path does NOT require
  ``CONSULT_API_KEY``.
- HTTP transport requires ``CONSULT_API_KEY`` in env — absent => exit 1
  with a clear stderr message; present => the factory is called with
  ``require_auth=True`` and ``api_key`` from env, then ``server.run`` is
  invoked with ``transport="streamable-http"`` and the parsed host/port
  set on ``server.settings``.
- Invalid ``--bind`` formatting is rejected with a clear error.
- When ``cosinabox.consult.build_consult_server`` is ``None`` (the graceful
  degrade sentinel for when the ``mcp`` extra isn't installed), the CLI
  exits 1 with install instructions — never a raw ``TypeError``.
"""

# ruff: noqa: I001  # see test_agent_failover.py — pre-commit/CI ruff version skew
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import click
import pytest
from click.testing import CliRunner

from cosinabox.cli.main import cli


def _fake_server() -> MagicMock:
    """A FastMCP-shaped stub: has ``.run()`` + a mutable ``.settings``."""
    server = MagicMock()
    server.settings = MagicMock()
    server.settings.host = "127.0.0.1"
    server.settings.port = 8000
    return server


def test_consult_serve_help_advertises_options() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["consult-serve", "--help"])
    assert result.exit_code == 0
    assert "--transport" in result.output
    assert "--bind" in result.output


def test_consult_serve_default_is_stdio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Omitting ``--transport`` should run stdio — the safest default."""
    server = _fake_server()
    builder = MagicMock(return_value=server)
    monkeypatch.setattr("cosinabox.cli.consult_serve.build_consult_server", builder)

    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "consult-serve"])
    assert result.exit_code == 0, result.output

    # build_consult_server called with config_dir and no auth (stdio).
    builder.assert_called_once()
    _, kwargs = builder.call_args
    assert kwargs.get("require_auth", False) is False
    assert kwargs.get("api_key") is None
    server.run.assert_called_once_with(transport="stdio")


def test_consult_serve_stdio_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    server = _fake_server()
    builder = MagicMock(return_value=server)
    monkeypatch.setattr("cosinabox.cli.consult_serve.build_consult_server", builder)

    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "consult-serve", "--transport", "stdio"])
    assert result.exit_code == 0, result.output
    server.run.assert_called_once_with(transport="stdio")


def test_consult_serve_http_without_api_key_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTP transport without CONSULT_API_KEY => exit 1 + stderr message.

    The factory must NOT be called — we fail at the CLI layer so we never
    bind an unauthenticated HTTP endpoint, even transiently.
    """
    builder = MagicMock()
    monkeypatch.setattr("cosinabox.cli.consult_serve.build_consult_server", builder)
    monkeypatch.delenv("CONSULT_API_KEY", raising=False)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["-C", str(tmp_path), "consult-serve", "--transport", "http"],
    )
    assert result.exit_code == 1
    assert "CONSULT_API_KEY" in result.stderr
    builder.assert_not_called()


def test_consult_serve_http_with_api_key_builds_with_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With CONSULT_API_KEY set, HTTP transport wires Bearer auth and calls
    ``server.run(transport="streamable-http", ...)`` with the parsed host +
    port copied onto ``server.settings``."""
    server = _fake_server()
    builder = MagicMock(return_value=server)
    monkeypatch.setattr("cosinabox.cli.consult_serve.build_consult_server", builder)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "-C",
            str(tmp_path),
            "consult-serve",
            "--transport",
            "http",
            "--bind",
            "127.0.0.1:8080",
        ],
        env={"CONSULT_API_KEY": "secret-token"},
    )
    assert result.exit_code == 0, result.output

    # Factory must be told to enforce auth + given the key from env.
    _, kwargs = builder.call_args
    assert kwargs["api_key"] == "secret-token"
    assert kwargs["require_auth"] is True

    # Host/port pushed onto server.settings before .run().
    assert server.settings.host == "127.0.0.1"
    assert server.settings.port == 8080
    server.run.assert_called_once_with(transport="streamable-http")


def test_consult_serve_http_bind_without_port_defaults_to_8080(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = _fake_server()
    builder = MagicMock(return_value=server)
    monkeypatch.setattr("cosinabox.cli.consult_serve.build_consult_server", builder)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "-C",
            str(tmp_path),
            "consult-serve",
            "--transport",
            "http",
            "--bind",
            "0.0.0.0",
        ],
        env={"CONSULT_API_KEY": "k"},
    )
    assert result.exit_code == 0, result.output
    assert server.settings.host == "0.0.0.0"
    assert server.settings.port == 8080


def test_consult_serve_http_invalid_bind_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--bind`` with a non-numeric port => clear error, exit 1."""
    builder = MagicMock()
    monkeypatch.setattr("cosinabox.cli.consult_serve.build_consult_server", builder)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "-C",
            str(tmp_path),
            "consult-serve",
            "--transport",
            "http",
            "--bind",
            "127.0.0.1:notaport",
        ],
        env={"CONSULT_API_KEY": "k"},
    )
    assert result.exit_code == 1
    assert "bind" in result.stderr.lower() or "port" in result.stderr.lower()
    builder.assert_not_called()


def test_consult_serve_when_mcp_extra_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the ``mcp`` extra isn't installed, ``build_consult_server`` is the
    ``None`` sentinel from ``cosinabox.consult.__init__``. The CLI must
    detect that and exit 1 with install instructions — not a ``TypeError``
    from calling ``None(...)``.
    """
    monkeypatch.setattr("cosinabox.cli.consult_serve.build_consult_server", None)

    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "consult-serve"])
    assert result.exit_code == 1
    assert "cosinabox[consult]" in result.stderr or "consult extra" in result.stderr.lower()


def test_consult_serve_passes_config_dir_to_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The factory receives the ``-C`` config_dir as its first positional."""
    server = _fake_server()
    captured: dict[str, Any] = {}

    def fake_builder(config_dir: Any, **kwargs: Any) -> Any:
        captured["config_dir"] = config_dir
        captured["kwargs"] = kwargs
        return server

    monkeypatch.setattr("cosinabox.cli.consult_serve.build_consult_server", fake_builder)

    runner = CliRunner()
    result = runner.invoke(cli, ["-C", str(tmp_path), "consult-serve"])
    assert result.exit_code == 0, result.output
    assert Path(captured["config_dir"]) == tmp_path


# A small sanity check that the command is registered on the CLI group —
# catches accidental removal from ``cli/main.py``.
def test_consult_serve_registered_on_cli() -> None:
    assert isinstance(cli.commands.get("consult-serve"), click.Command)
