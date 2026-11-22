from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx2
import pytest
import uvicorn
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent, TextResourceContents

from jdad.server import create_http_app

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TOOLS = {
    "list_topics",
    "search_practices",
    "get_practice",
    "list_sources",
    "get_source",
    "get_checklist",
    "kb_version",
}


def tool_payload(result) -> object:
    assert result.is_error is False, getattr(result, "content", result)
    data = result.structured_content
    if isinstance(data, dict) and "result" in data and len(data) == 1:
        return data["result"]
    if data is not None:
        return data
    texts = [block.text for block in result.content if isinstance(block, TextContent)]
    assert texts, result
    try:
        return json.loads(texts[0])
    except json.JSONDecodeError:
        return texts[0]


@pytest.mark.anyio
async def test_lists_every_tool_as_read_only(client: Client) -> None:
    listed = await client.list_tools()
    names = {tool.name for tool in listed.tools}
    assert EXPECTED_TOOLS <= names
    for tool in listed.tools:
        if tool.name in EXPECTED_TOOLS:
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.open_world_hint is False


@pytest.mark.anyio
async def test_list_topics_returns_performance(client: Client) -> None:
    topics = tool_payload(await client.call_tool("list_topics"))
    assert isinstance(topics, list)
    performance = next(item for item in topics if item["topic"] == "performance")
    assert performance["file"] == "practices/performance.md"
    assert "frontend" in performance["tags"]
    assert "db" in performance["tags"]
    assert "Frontend" in performance["headings"]
    assert "Database" in performance["headings"]


@pytest.mark.anyio
async def test_search_practices_returns_sections(client: Client) -> None:
    hits = tool_payload(
        await client.call_tool("search_practices", {"query": "OpenTelemetry", "tag": "observability"})
    )
    assert hits
    assert any(
        hit["heading"] and "OpenTelemetry" in hit["body"] and hit["file"].endswith("performance.md")
        for hit in hits
    )
    frontend_only = tool_payload(
        await client.call_tool("search_practices", {"query": "OpenTelemetry", "tag": "frontend"})
    )
    assert frontend_only == []


@pytest.mark.anyio
async def test_get_practice_returns_full_file(client: Client) -> None:
    text = tool_payload(await client.call_tool("get_practice", {"topic": "performance"}))
    assert isinstance(text, str)
    assert text.startswith("# Performance")
    assert "Rule zero" in text
    assert "Skeleton loaders" in text
    assert "connection pooling" in text


@pytest.mark.anyio
async def test_list_and_get_source(client: Client) -> None:
    sources = tool_payload(await client.call_tool("list_sources"))
    assert isinstance(sources, list)
    source = next(item for item in sources if "breakingbreach" in item["id"])
    assert source["title"]
    assert source["file"].startswith("sources/")
    body = tool_payload(await client.call_tool("get_source", {"id": source["id"]}))
    assert "31 items" in body or "verbatim" in body.lower()
    assert "Skeleton loading screens" in body


@pytest.mark.anyio
async def test_get_checklist_filters_tags(client: Client) -> None:
    checklist = tool_payload(
        await client.call_tool("get_checklist", {"tags": ["backend", "db"]})
    )
    assert isinstance(checklist, str)
    assert "Paginate every list endpoint" in checklist
    assert "Kill N+1" in checklist
    assert "Skeleton loaders" not in checklist
    assert "[backend]" in checklist
    assert "[db]" in checklist

    all_rules = tool_payload(await client.call_tool("get_checklist", {"tags": []}))
    assert "Skeleton loaders" in all_rules
    assert "OpenTelemetry" in all_rules
    assert "Test with CPU throttling" in all_rules


@pytest.mark.anyio
async def test_kb_version_tool(client: Client) -> None:
    info = tool_payload(await client.call_tool("kb_version"))
    assert isinstance(info, dict)
    assert info["sha"]
    assert info["sha"] != "unknown"
    assert info["newest_entry"] == "2026-11-22"
    assert "2026-11-22" in info["display"]


@pytest.mark.anyio
async def test_practice_resource_and_apply_kb_prompt(client: Client) -> None:
    templates = await client.list_resource_templates()
    uris = [template.uri_template for template in templates.resource_templates]
    assert any(uri.startswith("kb://practices/") for uri in uris)

    resource = await client.read_resource("kb://practices/performance")
    texts = [
        block.text
        for block in resource.contents
        if isinstance(block, TextResourceContents)
    ]
    assert texts
    assert "Rule zero" in texts[0]
    assert "CDN for static assets" in texts[0]

    prompts = await client.list_prompts()
    names = {prompt.name for prompt in prompts.prompts}
    assert "apply-kb" in names

    got = await client.get_prompt(
        "apply-kb",
        {"task": "speed up the dashboard", "tags": "frontend, observability"},
    )
    message_text = "\n".join(
        (block.text if isinstance(block, TextContent) else str(block))
        for message in got.messages
        for block in (message.content if isinstance(message.content, list) else [message.content])
    )
    assert "get_checklist" in message_text
    assert "cite" in message_text.lower()
    assert "speed up the dashboard" in message_text
    assert "frontend, observability" in message_text


@pytest.mark.anyio
async def test_stdio_entry_point_serves_performance_content() -> None:
    server = StdioServerParameters(
        command="uv",
        args=["run", "jdad-mcp"],
        cwd=str(REPO_ROOT),
        env={"KB_ROOT": str(REPO_ROOT)},
    )
    async with Client(server) as stdio_client:
        topics = tool_payload(await stdio_client.call_tool("list_topics"))
        assert any(item["topic"] == "performance" for item in topics)
        practice = tool_payload(
            await stdio_client.call_tool("get_practice", {"topic": "performance"})
        )
        assert "Skeleton loaders" in practice
        version = tool_payload(await stdio_client.call_tool("kb_version"))
        assert version["newest_entry"] == "2026-11-22"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _HttpServer:
    def __init__(self, port: int) -> None:
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        config = uvicorn.Config(
            create_http_app(),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        deadline = time.time() + 8
        while time.time() < deadline:
            if self._server.started:
                return
            time.sleep(0.05)
        raise RuntimeError("HTTP test server failed to start")

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)


@pytest.fixture
def http_server(kb_root: Path) -> _HttpServer:
    server = _HttpServer(_free_port())
    server.start()
    try:
        yield server
    finally:
        server.stop()


def test_healthz_is_open_and_returns_only_ok(http_server: _HttpServer) -> None:
    response = httpx2.get(f"{http_server.base}/healthz", timeout=5)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_http_mode_serves_performance_content(http_server: _HttpServer) -> None:
    async with Client(f"{http_server.base}/mcp") as http_client:
        topics = tool_payload(await http_client.call_tool("list_topics"))
        assert any(item["topic"] == "performance" for item in topics)
        practice = tool_payload(
            await http_client.call_tool("get_practice", {"topic": "performance"})
        )
        assert "Skeleton loaders" in practice
        version = tool_payload(await http_client.call_tool("kb_version"))
        assert version["newest_entry"] == "2026-11-22"
        assert version["sha"]


def test_http_bearer_auth_optional(monkeypatch: pytest.MonkeyPatch, kb_root: Path) -> None:
    token = "test-jdad-token-not-a-secret"
    monkeypatch.setenv("JDAD_TOKEN", token)
    server = _HttpServer(_free_port())
    server.start()
    try:
        open_health = httpx2.get(f"{server.base}/healthz", timeout=5)
        assert open_health.status_code == 200

        denied = httpx2.post(
            f"{server.base}/mcp",
            headers={"Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            timeout=5,
        )
        assert denied.status_code == 401

        accepted = httpx2.post(
            f"{server.base}/mcp",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "jdad-tests", "version": "0"},
                },
            },
            timeout=5,
        )
        assert accepted.status_code != 401
        assert accepted.status_code < 500
    finally:
        server.stop()


@pytest.mark.anyio
async def test_http_client_with_bearer_token(monkeypatch: pytest.MonkeyPatch, kb_root: Path) -> None:
    token = "test-jdad-token-not-a-secret"
    monkeypatch.setenv("JDAD_TOKEN", token)
    server = _HttpServer(_free_port())
    server.start()
    try:
        http = httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        async with (
            http,
            Client(streamable_http_client(f"{server.base}/mcp", http_client=http)) as mcp_client,
        ):
            practice = tool_payload(
                await mcp_client.call_tool("get_practice", {"topic": "performance"})
            )
            assert "Skeleton loaders" in practice
    finally:
        server.stop()



def test_default_http_bind_is_loopback() -> None:
    from jdad.server import parse_args

    args = parse_args(["--http"])
    assert args.host == "127.0.0.1"
    assert args.port == 8765
    assert args.allow_no_auth is False


def test_refuses_non_loopback_without_token(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    from jdad.server import NO_AUTH_BIND_WARNING, InsecureBindError, check_http_bind

    monkeypatch.delenv("JDAD_TOKEN", raising=False)
    with pytest.raises(InsecureBindError, match="refusing to bind 0.0.0.0"):
        check_http_bind("0.0.0.0", allow_no_auth=False)

    check_http_bind("127.0.0.1", allow_no_auth=False)
    check_http_bind("0.0.0.0", allow_no_auth=False, token="not-the-real-token")

    with caplog.at_level("WARNING"):
        check_http_bind("0.0.0.0", allow_no_auth=True)
    assert NO_AUTH_BIND_WARNING in caplog.text


class _HostPreservingProxy:
    """Reverse proxy that forwards to an upstream and keeps the client Host header."""

    def __init__(self, upstream_port: int) -> None:
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt: str, *args: object) -> None:
                return

            def _forward(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else None
                headers = {name: value for name, value in self.headers.items()}
                conn = http.client.HTTPConnection("127.0.0.1", upstream_port, timeout=5)
                try:
                    conn.request(self.command, self.path, body=body, headers=headers)
                    resp = conn.getresponse()
                    data = resp.read()
                finally:
                    conn.close()
                self.send_response(resp.status, resp.reason)
                for name, value in resp.getheaders():
                    if name.lower() in {"transfer-encoding", "connection"}:
                        continue
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                self._forward()

            def do_POST(self) -> None:
                self._forward()

            def do_DELETE(self) -> None:
                self._forward()

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = int(self._httpd.server_address[1])
        self.base = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._thread.join(timeout=5)
        self._httpd.server_close()


def _mcp_initialize(token: str) -> tuple[dict[str, str], dict]:
    return (
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "jdad-tests", "version": "0"},
            },
        },
    )


def test_parse_allowed_hosts_splits_and_strips(monkeypatch: pytest.MonkeyPatch) -> None:
    from jdad.server import parse_allowed_hosts, transport_security_settings

    assert parse_allowed_hosts("") == []
    assert parse_allowed_hosts("  ") == []
    assert parse_allowed_hosts("jdad.example") == ["jdad.example"]
    assert parse_allowed_hosts("jdad.example, other.example") == ["jdad.example", "other.example"]
    assert parse_allowed_hosts("https://jdad.example/mcp,") == ["jdad.example"]

    monkeypatch.setenv("JDAD_ALLOWED_HOSTS", "jdad.example")
    settings = transport_security_settings()
    assert settings.enable_dns_rebinding_protection is True
    assert "127.0.0.1:*" in settings.allowed_hosts
    assert "localhost:*" in settings.allowed_hosts
    assert "[::1]:*" in settings.allowed_hosts
    assert "jdad.example" in settings.allowed_hosts
    assert "jdad.example:*" in settings.allowed_hosts
    assert "https://jdad.example" in settings.allowed_origins
    assert "https://jdad.example:*" in settings.allowed_origins


def test_public_host_header_via_http_proxy(
    monkeypatch: pytest.MonkeyPatch, kb_root: Path
) -> None:
    """A public Host through a forwarding proxy is 421 unless allowlisted."""
    token = "test-jdad-token-not-a-secret"
    monkeypatch.setenv("JDAD_TOKEN", token)
    monkeypatch.delenv("JDAD_ALLOWED_HOSTS", raising=False)
    headers, payload = _mcp_initialize(token)

    def post_via_proxy(proxy: _HostPreservingProxy, host: str) -> httpx2.Response:
        # Talk to the proxy as if it were the public hostname: the request
        # URL is the proxy, but Host is the public name, which the proxy
        # forwards unchanged (the same way cloudflared preserves req.Host).
        return httpx2.post(
            f"{proxy.base}/mcp",
            headers={**headers, "Host": host},
            json=payload,
            timeout=5,
        )

    denied_server = _HttpServer(_free_port())
    denied_server.start()
    denied_proxy = _HostPreservingProxy(denied_server.port)
    denied_proxy.start()
    try:
        denied = post_via_proxy(denied_proxy, "jdad.example")
        assert denied.status_code == 421
        assert "Invalid Host header" in denied.text
    finally:
        denied_proxy.stop()
        denied_server.stop()

    monkeypatch.setenv("JDAD_ALLOWED_HOSTS", "jdad.example")
    allowed_server = _HttpServer(_free_port())
    allowed_server.start()
    allowed_proxy = _HostPreservingProxy(allowed_server.port)
    allowed_proxy.start()
    try:
        accepted = post_via_proxy(allowed_proxy, "jdad.example")
        assert accepted.status_code == 200
        # Loopback Host still works when a public name is also listed.
        loopback = httpx2.post(
            f"{allowed_server.base}/mcp",
            headers=headers,
            json=payload,
            timeout=5,
        )
        assert loopback.status_code == 200
        # A different public Host is still rejected.
        other = post_via_proxy(allowed_proxy, "not-listed.example")
        assert other.status_code == 421
    finally:
        allowed_proxy.stop()
        allowed_server.stop()


def test_allowed_hosts_include_public_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    from jdad.server import transport_security_settings

    monkeypatch.setenv("JDAD_ALLOWED_HOSTS", "jdad-mcp.jondevs.com")
    settings = transport_security_settings()
    assert settings.enable_dns_rebinding_protection is True
    assert "jdad-mcp.jondevs.com" in settings.allowed_hosts
    assert "jdad-mcp.jondevs.com:*" in settings.allowed_hosts
    assert "https://jdad-mcp.jondevs.com" in settings.allowed_origins
    assert "https://jdad-mcp.jondevs.com:*" in settings.allowed_origins


def test_quoted_empty_token_is_unset() -> None:
    from jdad.server import InsecureBindError, check_http_bind, normalize_secret

    assert normalize_secret("") == ""
    assert normalize_secret("   ") == ""
    assert normalize_secret('""') == ""
    assert normalize_secret("''") == ""
    assert normalize_secret('"secret"') == "secret"
    with pytest.raises(InsecureBindError, match="refusing to bind"):
        check_http_bind("0.0.0.0", allow_no_auth=False, token='""')


def test_http_initialize_reports_package_version(http_server: _HttpServer) -> None:
    from jdad import __version__

    response = httpx2.post(
        f"{http_server.base}/mcp",
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "jdad-tests", "version": "0"},
            },
        },
        timeout=5,
    )
    assert response.status_code == 200
    text = response.text
    if "data:" in text:
        lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
        text = lines[-1] if lines else text
    payload = json.loads(text)
    info = payload["result"]["serverInfo"]
    assert info["name"] == "jdad"
    assert info["version"] == __version__
