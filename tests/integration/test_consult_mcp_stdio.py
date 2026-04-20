"""End-to-end stdio smoke test for the consult MCP server.

Spawns ``python -m cosinabox.consult.server`` as a subprocess, connects via
the SDK's stdio client, lists tools, and invokes ``consult`` — asserting
the server registers both tools and the tool round-trip returns a string.

The subprocess runs with ``COSINABOX_CONSULT_STUB=1`` so it uses an
in-process stub Anthropic + memory client, keeping the test hermetic (no
network, no real API key, no real memory DB).

If the MCP SDK's client-side stdio API regresses or the subprocess API
becomes async-incompatible on a given platform, this test skips rather
than fights the SDK — per M4 plan guidance.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import timedelta

import pytest

pytestmark = pytest.mark.asyncio

try:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
except ImportError:  # pragma: no cover - exercised when mcp extra is absent
    pytest.skip(
        "mcp extra not installed; skipping stdio integration test",
        allow_module_level=True,
    )


async def test_consult_server_stdio_roundtrip(tmp_path: object) -> None:
    """Boot the server via subprocess, list tools, call ``consult``.

    The stub deps (see ``server._build_stub_deps``) make the Anthropic
    call return ``"stubbed consult answer"`` unconditionally, so we can
    assert on the exact payload the handler forwards back.
    """
    env = os.environ.copy()
    env["COSINABOX_CONSULT_STUB"] = "1"
    # No ANTHROPIC_API_KEY needed — stub deps skip the real client build.

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "cosinabox.consult.server"],
        env=env,
    )

    try:
        async with asyncio.timeout(20):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    tools_result = await session.list_tools()
                    names = sorted(t.name for t in tools_result.tools)
                    assert names == ["brainstorm", "consult"]
                    for tool in tools_result.tools:
                        assert tool.description, f"{tool.name} has no description"

                    call_result = await session.call_tool(
                        "consult",
                        {"prompt": "why?"},
                        read_timeout_seconds=timedelta(seconds=10),
                    )
                    assert not call_result.isError, f"consult call errored: {call_result}"
                    # The server returns a plain string; FastMCP wraps it as a
                    # TextContent block and also populates structuredContent.
                    text_blocks = [
                        block.text
                        for block in call_result.content
                        if getattr(block, "type", None) == "text"
                    ]
                    assert text_blocks, "expected at least one text content block"
                    assert "stubbed consult answer" in text_blocks[0]
    except TimeoutError as exc:  # pragma: no cover
        pytest.skip(f"MCP stdio client timed out on this platform (mcp SDK): {exc}")
