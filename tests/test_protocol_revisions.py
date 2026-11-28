"""MCP protocol revisions (roadmap P3.6, JON-1485).

With the pinned `mcp` SDK, the server must serve both eras on every transport (R-mcp-4):
- the handshake era (`initialize`, 2025-11-25), which target clients may still use; the
  server must not drop it while any target client row in the matrix fails on the new one;
- the stateless 2026-07-28 revision, reached through a real `server/discover` probe
  (`mode="auto"`; a pinned `mode="2026-07-28"` skips the probe, so it isn't evidence).

`docs/research/open-standards.md` keeps a matrix row per pinned SDK version, and a test
fails when the installed `mcp` has no row, so an SDK bump can't skip the check.
"""

from __future__ import annotations

import importlib.metadata
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx2
import pytest
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp_types.version import HANDSHAKE_PROTOCOL_VERSIONS

from jdad.server import mcp as jdad_server
from test_server import (  # tests/ is on sys.path (pytest's default import mode)
    _free_port,
    _HttpServer,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX = REPO_ROOT / "docs" / "research" / "open-standards.md"
HANDSHAKE = "2025-11-25"
STATELESS = "2026-07-28"
TRANSPORTS = ["in-process", "http", "stdio"]


@asynccontextmanager
async def connect(transport: str, mode: str) -> AsyncIterator[Client]:
    if transport == "in-process":
        async with Client(jdad_server, mode=mode) as client:
            yield client
    elif transport == "http":
        server = _HttpServer(_free_port())
        server.start()
        try:
            async with (
                httpx2.AsyncClient(timeout=10) as http,
                Client(streamable_http_client(f"{server.base}/mcp", http_client=http), mode=mode) as client,
            ):
                yield client
        finally:
            server.stop()
    else:
        params = StdioServerParameters(command="uv", args=["run", "jdad-mcp"])
        async with Client(stdio_client(params), mode=mode) as client:
            yield client


async def _kb_version_works(client: Client) -> None:
    tools = {tool.name for tool in (await client.list_tools()).tools}
    assert "kb_version" in tools
    result = await client.call_tool("kb_version", {})
    assert not result.is_error
    payload = result.structured_content or json.loads(result.content[0].text)
    assert payload.get("sha")


@pytest.mark.anyio
@pytest.mark.parametrize("transport", TRANSPORTS)
async def test_the_handshake_era_still_works(transport: str) -> None:
    """The server keeps serving `initialize` (no switch while a client row fails)."""
    assert HANDSHAKE in HANDSHAKE_PROTOCOL_VERSIONS
    async with connect(transport, "legacy") as client:
        assert client.protocol_version == HANDSHAKE
        assert client.session.initialize_result is not None
        await _kb_version_works(client)


@pytest.mark.anyio
@pytest.mark.parametrize("transport", TRANSPORTS)
async def test_server_discover_negotiates_the_stateless_revision(transport: str) -> None:
    async with connect(transport, "auto") as client:
        discover = client.session.discover_result
        assert discover is not None, "auto fell back to initialize: server/discover failed"
        assert STATELESS in discover.supported_versions
        assert client.protocol_version == STATELESS
        await _kb_version_works(client)


ROW_RE = re.compile(r"^\| `mcp` (\S+) [^|]*\| ([^|]+)\| ([^|]+)\|", re.MULTILINE)


def _sdk_rows() -> dict[str, tuple[str, str]]:
    return {m.group(1): (m.group(2).strip(), m.group(3).strip()) for m in ROW_RE.finditer(MATRIX.read_text())}


def test_the_matrix_has_a_row_for_the_pinned_sdk() -> None:
    """An SDK bump fails here until the matrix gets a row for the new version."""
    version = importlib.metadata.version("mcp")
    rows = _sdk_rows()
    assert version in rows, f"docs/research/open-standards.md has no matrix row for mcp {version}: {sorted(rows)}"
    initialize, discover = rows[version]
    assert initialize.startswith("pass"), initialize  # the two tests above, for this version
    assert discover.startswith("pass"), discover
