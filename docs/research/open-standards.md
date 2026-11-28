# Open standards: AGENTS.md, Agent Skills, Agent Plugins, MCP

Date checked: 2026-11-22.

## AGENTS.md

Source: https://agents.md (repo: https://github.com/agentsmd/agents.md)

- "A simple, open format for guiding coding agents, used by over 60k open-source projects." "Think of AGENTS.md as a README for agents."
- No required fields: "AGENTS.md is just standard Markdown." Suggested sections: project overview, build and test commands, code style, testing instructions, security considerations, commit and PR guidelines.
- Nested files: "Agents automatically read the nearest file in the directory tree, so the closest one takes precedence." "The closest AGENTS.md to the edited file wins; explicit user chat prompts override everything."
- Agents run the checks it lists: "The agent will attempt to execute relevant programmatic checks and fix failures before finishing the task."
- Stewarded by the Agentic AI Foundation under the Linux Foundation. Listed adopters include Codex, Cursor, Jules, Factory, Aider, goose, opencode, Zed, Warp, VS Code, Devin, Junie, Amp, RooCode, Gemini CLI, GitHub Copilot's coding agent, Windsurf, Augment Code.
- Claude Code reads it only when no `CLAUDE.md` exists, or through an `@AGENTS.md` import (see [claude-code.md](claude-code.md)). Grok Build reads it alongside `CLAUDE.md` (see [grok-build.md](grok-build.md)).

## Agent Skills

Sources: https://agentskills.io/specification, https://agentskills.io/clients, https://github.com/agentskills/agentskills

- A skill is a directory with `SKILL.md` plus optional `scripts/`, `references/`, `assets/`.
- Frontmatter: `name` (required, 1–64 chars, lowercase letters, digits, hyphens; no leading, trailing or double hyphens; must match the directory name), `description` (required, ≤1024 chars, what it does and when to use it), `license`, `compatibility` (≤500 chars), `metadata` (string map), `allowed-tools` (experimental).
- Progressive disclosure: metadata ~100 tokens at startup; body "< 5000 tokens recommended" on activation; resources on demand. "Keep your main `SKILL.md` under 500 lines." "Keep file references one level deep."
- Validator: `skills-ref validate ./my-skill`.
- Clients include Claude Code, Codex, Cursor, Gemini CLI, GitHub Copilot, OpenCode, Amp, Goose, Factory. Grok Build is not in the list but documents compatible `SKILL.md` loading.

## Agent Plugins

Sources: https://agent-plugins.org, https://cursor.com/docs/plugins, https://developers.openai.com/plugins/build/plugins

- "An open, vendor-neutral standard for packaging reusable components into portable plugins." Version 1.0.0 covers Agent Skills and MCP servers.
- Layout: `plugin.json` at the root, `skills/`, `mcp.json`, and reverse-domain folders for client extensions (for example `com.example.client/hooks/`).
- Steering committee: Amazon, Cursor, Microsoft, OpenAI, Vercel. Cursor and Codex document support. Claude Code and Grok Build docs read did not mention it.

## Model Context Protocol

Sources: https://modelcontextprotocol.io/specification/2026-07-28, https://modelcontextprotocol.io/specification/2026-07-28/changelog.md, https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices.md

- The current revision is **2026-07-28** (previous: 2025-11-25). Major changes: no protocol-level sessions or `Mcp-Session-Id`; no `initialize` handshake (each request carries protocol version and capabilities in `_meta`); a required `server/discover` RPC; `subscriptions/listen` replaces the GET endpoint and resource subscribe; `ping` and `logging/setLevel` removed; tasks moved to an extension; Multi Round-Trip Requests replace server-initiated requests.
- Authorization for HTTP servers is OAuth 2.1-based; JDAD uses a static bearer token, which clients support through headers.

### Protocol revision matrix (P3.6)

The JDAD server serves both eras: the handshake era (`initialize`, 2025-11-25) and the stateless 2026-07-28 revision (`server/discover`, no session). It must not drop the handshake era while any target client row below fails or is unchecked.

One row per pinned SDK version. `tests/test_protocol_revisions.py` produces these results, and it fails when the installed `mcp` has no row here.

| SDK (pinned) | `initialize` (2025-11-25) | `server/discover` (2026-07-28) | Checked |
| --- | --- | --- | --- |
| `mcp` 2.3.0 (`mcp-types` 2.3.0) | pass on in-process, HTTP and stdio (`mode="legacy"`) | pass on in-process, HTTP and stdio (`mode="auto"` probes discover and negotiates 2026-07-28) | 2026-11-27, JON-1485 |

Target clients, each run against a **local** JDAD server on loopback (no token; a throwaway `HOME` so no real client config was touched; never the production endpoint), with a logging wrapper recording the revision each request carried:

| Client | Version | What it sent | Result |
| --- | --- | --- | --- |
| Claude Code | 2.1.332 | 2026-07-28: `server/discover`, then `subscriptions/listen` and `tools/list` (all 200) | pass: `claude mcp list` shows Connected |
| Grok Build | 1.0.77 | 2026-07-28: `server/discover`, then `tools/list` (all 200) | pass: `grok mcp doctor` shows handshake OK (protocol 2026-07-28), 8 tools |
| Codex | 0.155.1 | no MCP request: `codex mcp list` and `codex mcp get` only probe OAuth metadata (GETs, 404) | not checked: the handshake happens only inside a model session (`codex exec`), which needs a login and model calls |
| Cursor | cursor-agent 2026.09.18-9a7762b | nothing (it didn't start) | not checked: `cursor-agent mcp` needs the macOS login keychain, so it can't run under a throwaway `HOME` |

Checked 2026-11-27 (JON-1485). Two clients are unchecked, so the server keeps the handshake era.

## Borrow / skip

| Call | What | Why |
| --- | --- | --- |
| Borrow | `AGENTS.md` as the canonical instructions file in every harness template | Widest support; one file |
| Borrow | Agent Skills spec as JDAD's canonical skill format, spec-only frontmatter in the source | Loads everywhere; tool extras added by the compiler |
| Borrow | `skills-ref validate` (or an equivalent check) in `./verify` | Catches the naming rules (directory = name) early |
| Borrow | Agent Plugins as the Codex and Cursor distribution package | One package for two tools |
| Borrow | MCP 2026-07-28 statelessness | `mcp` 2.3.0 serves it alongside `initialize`, and Claude Code and Grok Build already use it (P3.6, matrix above). Keep the handshake era while any target client is unchecked or fails |
| Skip | OAuth 2.1 for the JDAD server for now | Single user, read-only KB; a bearer token is enough. Revisit if others get access |
