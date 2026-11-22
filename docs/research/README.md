# Research notes

One file per area. Each file lists key facts, short quotes, source URLs, the date checked, and a borrow/skip call for JDAD.

All sources were read on **2026-11-22** from primary documentation (vendor docs, specs, official engineering posts, or the repo itself). Where a fact could not be confirmed from a primary source, the file says so under **Unverified**.

| File | Area |
| --- | --- |
| [claude-code.md](claude-code.md) | Claude Code: CLAUDE.md, rules, skills, plugins and marketplaces, subagents, hooks, output styles, settings and permissions, MCP, headless, plugin evals |
| [codex.md](codex.md) | OpenAI Codex CLI: AGENTS.md, config.toml, MCP, skills, plugins, hooks, subagents, sandbox and approvals, `codex exec` |
| [grok-build.md](grok-build.md) | xAI Grok Build: instructions files, skills, plugins and marketplaces, hooks, MCP, permissions, headless |
| [cursor.md](cursor.md) | Cursor: rules, AGENTS.md, skills, hooks, MCP, plugins, the `agent` CLI |
| [open-standards.md](open-standards.md) | AGENTS.md, Agent Skills, Agent Plugins, and the MCP spec |
| [harness-engineering.md](harness-engineering.md) | Anthropic and OpenAI on agents, context, long-running harnesses; spec-driven development; verification and review loops; lessons files |
| [community-setups.md](community-setups.md) | The community catalogs and setups worth borrowing from |

## Cross-tool summary (as of 2026-11-22)

| Concern | Claude Code | Codex CLI | Grok Build | Cursor |
| --- | --- | --- | --- | --- |
| Instructions file | `CLAUDE.md` (reads `AGENTS.md` only when no `CLAUDE.md` exists; `@AGENTS.md` import works) | `AGENTS.md` (+ `AGENTS.override.md`) | `AGENTS.md` **and** `CLAUDE.md` (loads every match) | `AGENTS.md` or `.cursor/rules/*.mdc` |
| Scoped rules | `.claude/rules/` with `paths:` | nested `AGENTS.md` | `.grok/rules/*.md` (also reads `.claude/rules/`, `.cursor/rules/`) | `.mdc` with `globs` / `alwaysApply` |
| Skills (Agent Skills spec) | `.claude/skills/`, plugin `skills/` | `.agents/skills/` | `.grok/skills/`, `~/.agents/skills/`, Claude skills | `.agents/skills/`, `.cursor/skills/`, also `.claude/skills/`, `.codex/skills/` |
| MCP config | `.mcp.json`, `claude mcp add` | `[mcp_servers]` in `config.toml`, `codex mcp add` | `[mcp_servers]` in `.grok/config.toml`; also reads `.mcp.json`, `.cursor/mcp.json` | `.cursor/mcp.json`, `agent mcp` |
| Hooks | `.claude/settings.json` (30+ events) | `.codex/hooks.json` or `[hooks]` | `.grok/hooks/*.json`; also reads Claude and Cursor hooks | `.cursor/hooks.json`; can load Claude hooks |
| Plugins | `.claude-plugin/plugin.json` + `marketplace.json` | Agent Plugins `plugin.json` or `.codex-plugin/plugin.json`; `.agents/plugins/marketplace.json` | Reads Claude marketplaces and plugins; own `.grok-plugin/marketplace.json` | Agent Plugins or `.cursor-plugin/plugin.json` |
| Headless | `claude -p --bare` | `codex exec` | `grok -p --output-format json` | `agent -p [--force]` |

The portable floor is **AGENTS.md + Agent Skills + MCP**, with **Agent Plugins** as the emerging packaging standard. JDAD writes to that floor once and adds thin per-tool adapters only where a tool needs them.
