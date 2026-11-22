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

## Borrow / skip

| Call | What | Why |
| --- | --- | --- |
| Borrow | `AGENTS.md` as the canonical instructions file in every harness template | Widest support; one file |
| Borrow | Agent Skills spec as JDAD's canonical skill format, spec-only frontmatter in the source | Loads everywhere; tool extras added by the compiler |
| Borrow | `skills-ref validate` (or an equivalent check) in `./verify` | Catches the naming rules (directory = name) early |
| Borrow | Agent Plugins as the Codex and Cursor distribution package | One package for two tools |
| Watch | MCP 2026-07-28 statelessness | JDAD's tools are already stateless; track Python SDK support before upgrading (P3.6) |
| Skip | OAuth 2.1 for the JDAD server for now | Single user, read-only KB; a bearer token is enough. Revisit if others get access |
