# 0003: One read-only MCP server: stdio locally, streamable HTTP when hosted

- Status: Accepted (records what is on `main` as of 4a53412, from PR #1)
- Date: 2026-11-22
- Deciders: Jon, roadmap author

## Context

Agents on Jon's Mac and hosts can run local commands; cloud agents can't. Jon wants hosts to pick up new KB entries without reinstalling. All four target tools support stdio and streamable HTTP MCP servers with custom headers (Claude Code `.mcp.json`; Codex `bearer_token_env_var`; Grok Build `headers` with `${VAR}`; Cursor `mcp.json`). The MCP spec revision 2026-07-28 makes the protocol stateless, which fits a read-only server.

This ADR covers only what is merged. The hosted deployment (Docker on the droplet, Cloudflare TLS, the real hostname) is pending in PR #2 and is recorded separately as [ADR 0005](0005-hosted-deploy-cloudflare-full-strict.md), status Proposed.

## Decision

1. One codebase, `jdad-mcp`: stdio by default, streamable HTTP with `--http`.
2. Over HTTP the server requires a bearer token (`JDAD_TOKEN`), keeps DNS-rebinding protection on with a host allowlist (`JDAD_ALLOWED_HOSTS` adds public names), and refuses a non-loopback bind without a token unless `--allow-no-auth` is passed.
3. The server is read-only and offline: no writes to the KB, no outbound network, no model calls. Tools that sound active (`review_against_kb`, `bootstrap_repo`) return rules, rubrics or file manifests; the calling agent does the work.
4. The plugin's `.mcp.json` is an HTTP entry with a placeholder URL (`https://jdad.example/mcp` on `main`) and `${JDAD_TOKEN}` plus optional Cloudflare Access headers. stdio from a checkout stays supported for offline work and tests.

## Consequences

- Once a hosted URL is set (ADR 0005), new KB entries reach every host as soon as the server updates.
- No server-side LLM cost or secrets beyond the bearer token.
- Upgrading to the stateless MCP revision waits on SDK support (P3.6).

## Alternatives considered

- **stdio only**: no cloud-agent access and stale content between pulls. Rejected as the default.
- **Server-side review with a model API**: adds cost, secrets and network calls. Rejected; the agent already has a model.
- **OAuth 2.1**: the spec's general answer for HTTP auth, but overkill for one user and a read-only KB. Revisit if others get access.
