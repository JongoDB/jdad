"""JDAD MCP server: stdio or streamable HTTP, read-only knowledge base."""

from __future__ import annotations

import argparse
import hmac
import logging
import os
import stat
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from jdad import __version__
from jdad.kb import KnowledgeBase

logger = logging.getLogger("jdad")

READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

mcp = MCPServer(
    "jdad",
    version=__version__,
    instructions=(
        "Read-only knowledge base of Jon's agentic-dev practices (JDAD). "
        "Call get_checklist or search_practices before planning, and cite the "
        "rules you follow in the PR. Call kb_version when you need the SHA or "
        "the date of the newest entry."
    ),
)


def _kb() -> KnowledgeBase:
    # Resolved on each call so KB_ROOT and fresh files are picked up without a restart.
    return KnowledgeBase()


@mcp.tool(annotations=READ_ONLY)
def list_topics() -> list[dict[str, Any]]:
    """List practice files with their tags and section headings."""
    return _kb().list_topics()


@mcp.tool(annotations=READ_ONLY)
def search_practices(query: str, tag: str | None = None) -> list[dict[str, Any]]:
    """Keyword search over practice sections, returning matched file, heading, and body.

    Optional tag filter: frontend, backend, db, infra, observability, or testing.
    """
    return _kb().search_practices(query, tag=tag)


@mcp.tool(annotations=READ_ONLY)
def get_practice(topic: str) -> str:
    """Return the full practice file for a topic (for example, 'performance')."""
    return _kb().get_practice(topic)


@mcp.tool(annotations=READ_ONLY)
def list_sources() -> list[dict[str, Any]]:
    """List source notes that the practice rules were drawn from."""
    return _kb().list_sources()


@mcp.tool(annotations=READ_ONLY)
def get_source(id: str) -> str:
    """Return a source note by id (filename stem, for example '2026-11-22-breakingbreach-app-performance')."""
    return _kb().get_source(id)


@mcp.tool(annotations=READ_ONLY)
def get_checklist(tags: list[str]) -> str:
    """Return bullet rules filtered by tags, ready to paste into a plan.

    Tags: frontend, backend, db, infra, observability, testing. An empty list returns every rule.
    """
    return _kb().get_checklist(tags)


@mcp.tool(annotations=READ_ONLY)
def kb_version() -> dict[str, Any]:
    """Return the knowledge-base version: git SHA and the date of the newest source entry."""
    return _kb().version()


@mcp.resource("kb://practices/{name}")
def practice_resource(name: str) -> str:
    """A practice file from the knowledge base."""
    return _kb().get_practice(name)


@mcp.prompt(name="apply-kb")
def apply_kb(task: str = "", tags: str = "") -> str:
    """Tell an agent to pull the relevant KB checklist before planning and to cite rules in its PR."""
    tag_hint = f" Focus on these tags: {tags.strip()}." if tags.strip() else ""
    task_block = f"\n\nThe current task is:\n{task.strip()}\n" if task.strip() else ""
    return f"""You have access to the jdad MCP server, Jon's agentic-dev knowledge base (JDAD).

Before you write a plan or start implementation:{tag_hint}
1. Call list_topics to see available practice files and tags.
2. Call get_checklist with the tags that apply to this work (frontend, backend, db, infra, observability, testing). If you are unsure which tags apply, call search_practices with keywords from the task.
3. Pull the relevant checklist into your plan. Do not invent rules that are not in the KB, and do not apply a rule whose tag does not fit the work.
4. When you open a PR, cite the specific KB rules you followed (topic, heading, and the source noted on the rule).

Rule zero: when changing performance, measure first. Profile or trace, fix the top bottleneck, re-measure, and put before/after numbers in the PR.
{task_block}"""


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_request: Request) -> Response:
    """Liveness probe. Unauthenticated even when JDAD_TOKEN is set."""
    return JSONResponse({"status": "ok"})


def normalize_secret(raw: str | None) -> str:
    """Treat empty, whitespace-only, and quote-wrapped-empty values as unset.

    `docker run --env-file` with `JDAD_TOKEN=""` passes the literal quotes;
    Compose strips them. Either form must be treated as no token.
    """
    if raw is None:
        return ""
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text


class TokenConfigError(ValueError):
    """The bearer token configuration is unusable. Messages never include the token."""


def resolve_token() -> str:
    """The bearer token, or "" for none.

    ``JDAD_TOKEN_FILE`` (a file holding only the token, readable by this
    process and by nobody in its group or others) is the deploy path: the
    value stays out of the container environment and ``docker inspect``.
    ``JDAD_TOKEN`` still works when no file is configured. Setting both is
    an error, so a half-finished migration fails loudly instead of quietly
    using the old value.
    """
    env_token = normalize_secret(os.environ.get("JDAD_TOKEN"))
    path_text = (os.environ.get("JDAD_TOKEN_FILE") or "").strip()
    if not path_text:
        return env_token
    if env_token:
        raise TokenConfigError(
            "both JDAD_TOKEN and JDAD_TOKEN_FILE are set; remove JDAD_TOKEN from the "
            "environment (see deploy/migrate-token.sh)"
        )
    path = Path(path_text)
    try:
        mode = path.stat().st_mode
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TokenConfigError(
            f"cannot read JDAD_TOKEN_FILE {path_text}: {exc.strerror or exc.__class__.__name__}"
        ) from None
    except UnicodeDecodeError:
        raise TokenConfigError(f"JDAD_TOKEN_FILE {path_text} is not UTF-8 text") from None
    if not stat.S_ISREG(mode):
        raise TokenConfigError(f"JDAD_TOKEN_FILE {path_text} is not a regular file")
    if mode & 0o077:
        raise TokenConfigError(
            f"JDAD_TOKEN_FILE {path_text} is readable by group or others "
            f"(mode {stat.S_IMODE(mode):o}); chmod 400"
        )
    token = normalize_secret(raw)
    if not token:
        raise TokenConfigError(f"JDAD_TOKEN_FILE {path_text} is empty")
    return token


def _configured_token() -> str:
    return resolve_token()


def _bearer_token(header: str | None) -> str | None:
    if not header:
        return None
    scheme, _, rest = header.partition(" ")
    if scheme.lower() != "bearer" or not rest.strip():
        return None
    return rest.strip()


def _tokens_match(provided: str, expected: str) -> bool:
    a = provided.encode("utf-8")
    b = expected.encode("utf-8")
    if len(a) != len(b):
        hmac.compare_digest(b, b)
        return False
    return hmac.compare_digest(a, b)


class BearerAuthMiddleware:
    """Require Authorization: Bearer <token> when a token is configured.

    The token comes from JDAD_TOKEN_FILE or JDAD_TOKEN, resolved once when the
    app is built (see resolve_token). /healthz is always open. With no token,
    no auth is required.
    """

    def __init__(self, app: Any, token: str | None = None) -> None:
        self.app = app
        self.token = resolve_token() if token is None else normalize_secret(token)

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        if path.rstrip("/") == "/healthz":
            await self.app(scope, receive, send)
            return
        expected = self.token
        if not expected:
            await self.app(scope, receive, send)
            return
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers") or []
        }
        provided = _bearer_token(headers.get("authorization"))
        if provided is None or not _tokens_match(provided, expected):
            response = JSONResponse({"error": "unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)



def is_loopback(host: str) -> bool:
    return host.strip().lower() in {"127.0.0.1", "::1", "localhost"}


NO_AUTH_BIND_WARNING = (
    "jdad-mcp: binding to a non-loopback address without JDAD_TOKEN; "
    "the MCP endpoint is unauthenticated. Set JDAD_TOKEN or bind to 127.0.0.1."
)


class InsecureBindError(SystemExit):
    """Raised when HTTP would listen off-loopback with no token and no override."""


def check_http_bind(host: str, *, allow_no_auth: bool, token: str | None = None) -> None:
    """Refuse a non-loopback bind without a token unless --allow-no-auth is set."""
    if is_loopback(host):
        return
    expected = normalize_secret(token if token is not None else _configured_token())
    if expected:
        return
    if allow_no_auth:
        logger.warning(NO_AUTH_BIND_WARNING)
        return
    raise InsecureBindError(
        "jdad-mcp: refusing to bind "
        f"{host} without JDAD_TOKEN. Set JDAD_TOKEN or pass --allow-no-auth (insecure)."
    )


# Loopback Host/Origin values the MCP SDK allows by default for localhost binds.
# Always included; JDAD_ALLOWED_HOSTS only adds public names. Protection stays on.
_LOOPBACK_HOSTS = ("127.0.0.1:*", "localhost:*", "[::1]:*")
_LOOPBACK_ORIGINS = (
    "http://127.0.0.1:*",
    "http://localhost:*",
    "http://[::1]:*",
    "https://127.0.0.1:*",
    "https://localhost:*",
    "https://[::1]:*",
)


class AllowedHostsError(ValueError):
    """JDAD_ALLOWED_HOSTS has an entry the server refuses to trust."""


def parse_allowed_hosts(raw: str | None = None) -> list[str]:
    """Parse JDAD_ALLOWED_HOSTS: comma-separated public hostnames.

    Loopback is not required here; it is always merged in later. A pasted
    URL has its scheme and path stripped. Empty and whitespace-only items
    are ignored. Entries are lowercased, because Host matching is exact and
    DNS names are case-insensitive. Wildcards (``*``) are rejected: they
    would not match anything useful, and silently accepting them hides a
    misconfiguration.
    """
    text = os.environ.get("JDAD_ALLOWED_HOSTS", "") if raw is None else raw
    hosts: list[str] = []
    for part in text.split(","):
        item = part.strip()
        if not item:
            continue
        if "://" in item:
            item = item.split("://", 1)[1]
        item = item.split("/", 1)[0].strip().lower()
        if "*" in item:
            raise AllowedHostsError(
                f"JDAD_ALLOWED_HOSTS: wildcard entry {part.strip()!r} is not supported; "
                "list each public hostname"
            )
        if item and item not in hosts:
            hosts.append(item)
    return hosts


def _host_allow_entries(hostname: str) -> list[str]:
    entries = [hostname]
    if not hostname.endswith(":*") and ":" not in hostname.rstrip("]"):
        # Bare hostname (typical of a TLS frontend on 443) plus any port.
        entries.append(f"{hostname}:*")
    elif ":" in hostname and not hostname.endswith(":*") and not hostname.startswith("["):
        # Explicit host:port already covers that one value.
        pass
    return entries


def _origin_allow_entries(hostname: str) -> list[str]:
    host = hostname.removesuffix(":*")
    # Public hosts get https origins only; loopback http origins are in
    # _LOOPBACK_ORIGINS. IPv6 in Host is [::1] or [::1]:port.
    origins: list[str] = []
    for scheme in ("https",):
        if host.endswith(":*") or ":" not in host.rstrip("]"):
            origins.append(f"{scheme}://{host}")
            if not host.endswith(":*"):
                origins.append(f"{scheme}://{host}:*")
        else:
            origins.append(f"{scheme}://{host}")
    return origins


def transport_security_settings() -> TransportSecuritySettings:
    """DNS-rebinding settings for streamable HTTP. Protection is never disabled."""
    allowed_hosts = list(_LOOPBACK_HOSTS)
    allowed_origins = list(_LOOPBACK_ORIGINS)
    for hostname in parse_allowed_hosts():
        for entry in _host_allow_entries(hostname):
            if entry not in allowed_hosts:
                allowed_hosts.append(entry)
        for entry in _origin_allow_entries(hostname):
            if entry not in allowed_origins:
                allowed_origins.append(entry)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


def create_http_app(token: str | None = None):
    """Starlette app for streamable HTTP, with optional bearer auth and /healthz.

    ``token`` is the already-resolved bearer token; None resolves it now.
    """
    app = mcp.streamable_http_app(transport_security=transport_security_settings())
    app.add_middleware(BearerAuthMiddleware, token=resolve_token() if token is None else token)
    return app


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="jdad-mcp",
        description="JDAD knowledge-base MCP server (stdio or streamable HTTP).",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve Streamable HTTP instead of stdio.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP bind host (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="HTTP port (default: 8765).",
    )
    parser.add_argument(
        "--allow-no-auth",
        action="store_true",
        help="Allow a non-loopback HTTP bind when JDAD_TOKEN is unset (logs a warning).",
    )
    parser.add_argument(
        "--ssl-certfile",
        default=None,
        help="PEM certificate for HTTPS (or set JDAD_SSL_CERTFILE).",
    )
    parser.add_argument(
        "--ssl-keyfile",
        default=None,
        help="PEM private key for HTTPS (or set JDAD_SSL_KEYFILE).",
    )
    return parser.parse_args(argv)


def resolve_ssl_files(
    certfile: str | None = None, keyfile: str | None = None
) -> tuple[str | None, str | None]:
    """Return (cert, key) or (None, None). Both must be set together."""
    cert = (certfile or os.environ.get("JDAD_SSL_CERTFILE") or "").strip()
    key = (keyfile or os.environ.get("JDAD_SSL_KEYFILE") or "").strip()
    if cert and key:
        if not os.path.isfile(cert) or not os.path.isfile(key):
            raise SystemExit(
                "jdad-mcp: SSL certificate or key file is missing "
                f"(cert={cert!r} key={key!r})"
            )
        return cert, key
    if cert or key:
        raise SystemExit(
            "jdad-mcp: both --ssl-certfile and --ssl-keyfile "
            "(or JDAD_SSL_CERTFILE and JDAD_SSL_KEYFILE) are required together"
        )
    return None, None


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    if args.http:
        import uvicorn

        try:
            token = resolve_token()
        except TokenConfigError as exc:
            raise SystemExit(f"jdad-mcp: {exc}") from None
        check_http_bind(args.host, allow_no_auth=args.allow_no_auth, token=token)
        try:
            parse_allowed_hosts()
        except AllowedHostsError as exc:
            raise SystemExit(f"jdad-mcp: {exc}") from exc
        cert, key = resolve_ssl_files(args.ssl_certfile, args.ssl_keyfile)
        run_kw: dict[str, object] = {"host": args.host, "port": args.port}
        if cert and key:
            run_kw["ssl_certfile"] = cert
            run_kw["ssl_keyfile"] = key
        uvicorn.run(create_http_app(token), **run_kw)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
