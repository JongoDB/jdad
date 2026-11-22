# 0003: One read-only MCP server: stdio locally, streamable HTTP hosted

- Status: Accepted (records PR #1 and PR #2's design)
- Date: 2026-11-22
- Deciders: Jon, roadmap author

## Context

Agents on Jon's Mac and hosts can run local commands; cloud agents can't. Jon wants hosts to pick up new KB entries without reinstalling. All four target tools support stdio and streamable HTTP MCP servers with custom headers (Claude Code `.mcp.json`; Codex `bearer_token_env_var`; Grok Build `headers` with `${VAR}`; Cursor `mcp.json`). The MCP spec revision 2026-07-28 makes the protocol stateless, which fits a read-only server.

## Decision

1. One codebase, `jdad-mcp`: stdio by default, streamable HTTP with `--http`.
2. Hosted at `https://jdad-mcp.jondevs.com/mcp` behind Cloudflare, bearer token required (`JDAD_TOKEN`), host allowlist, loopback bind unless a token is set.
3. The server is read-only and offline: no writes to the KB, no outbound network, no model calls. Tools that sound active (`review_against_kb`, `bootstrap_repo`) return rules, rubrics or file manifests; the calling agent does the work.
4. The default plugin config points at the hosted URL. stdio from a checkout stays supported for offline work and tests.

## Consequences

- New KB entries reach every host as soon as the server updates.
- The droplet is a dependency; stdio is the fallback when it's down.
- No server-side LLM cost or secrets beyond the bearer token.
- Upgrading to the stateless MCP revision waits on SDK support (P3.6).

## Alternatives considered

- **stdio only**: no cloud-agent access and stale content between pulls. Rejected as the default.
- **Server-side review with a model API**: adds cost, secrets and network calls. Rejected; the agent already has a model.
- **OAuth 2.1**: the spec's general answer for HTTP auth, but overkill for one user and a read-only KB. Revisit if others get access.
