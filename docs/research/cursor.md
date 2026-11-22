# Cursor

Date checked: 2026-11-22. Source: the official docs at cursor.com/docs (markdown versions, `<page>.md`; index at https://cursor.com/llms.txt).

## Rules and AGENTS.md

Source: https://cursor.com/docs/rules

- Project rules live in `.cursor/rules/` as `.mdc` files. "A plain `.md` file in `.cursor/rules` is ignored by the rules system because it has no frontmatter."
- Frontmatter: `description`, `globs` (comma-separated path patterns), `alwaysApply`. Types: Always Apply, Apply Intelligently (by description), Apply to Specific Files (globs), Apply Manually (@-mention).
- `AGENTS.md` is supported as "a simple alternative to `.cursor/rules`." Team rules come from the dashboard on Team and Enterprise plans.

## Skills

Source: https://cursor.com/docs/skills

- Locations: `.agents/skills/`, `.cursor/skills/` (project); `~/.agents/skills/`, `~/.cursor/skills/` (user). Nested folders in monorepos are discovered.
- "For compatibility, Cursor also loads skills from Claude and Codex directories: `.claude/skills/`, `.codex/skills/`, `~/.claude/skills/`, and `~/.codex/skills/`."
- Cursor is listed as an Agent Skills client on https://agentskills.io/clients.

## Hooks

Source: https://cursor.com/docs/hooks

- `.cursor/hooks.json` (project) and `~/.cursor/hooks.json` (user). Cloud agents run project hooks but not user hooks.
- "Cursor supports loading hooks from third-party tools like Claude Code."

## MCP

Sources: https://cursor.com/docs/mcp, https://cursor.com/docs/cli/mcp

- `mcp.json` with an `mcpServers` object (stdio `command`/`args`/`env`, or remote `url`/`headers`). Static OAuth client credentials are supported.
- CLI: `agent mcp list`, `agent mcp list-tools <id>`, `agent mcp login <id>`, `agent mcp enable|disable <id>`.

## Plugins

Source: https://cursor.com/docs/plugins

- "Cursor supports the Agent Plugins open standard alongside its own plugin format." Agent Plugins: root `plugin.json` with skills and MCP servers. Cursor Plugins: `.cursor-plugin/plugin.json`, adding rules, agents, commands, hooks and variables.
- Cursor doesn't expand the standard's `${PLUGIN_ROOT}` / `${PLUGIN_DATA}` in `mcp.json`; use `${CURSOR_PLUGIN_ROOT}`.
- Cursor Marketplace plugins are manually reviewed. Team marketplaces (Teams: 1, Enterprise: unlimited) can distribute both formats.

## CLI

Sources: https://cursor.com/docs/cli/overview, https://cursor.com/docs/cli/headless

- Install `curl https://cursor.com/install -fsS | bash`, run `agent` (older docs and scripts call it `cursor-agent`).
- Print mode: `agent -p "<prompt>"`; `--force` (or `--yolo`) runs every action without approval except what `permissions.deny` and team policy block. Print mode writes files even without `--force`.
- Subagents work in the editor, CLI and Cloud Agents (https://cursor.com/docs/subagents).

## Borrow / skip

| Call | What | Why |
| --- | --- | --- |
| Borrow | Root `AGENTS.md` instead of generating many `.mdc` files | Cursor reads it; one source of truth |
| Borrow | Compile only **always-on, file-scoped** rules to `.cursor/rules/*.mdc` (with `globs`) | Skills already load from `.agents/skills`; `.mdc` adds what skills can't: glob scoping |
| Borrow | Skills in `.agents/skills/` | Read natively, no Cursor-specific copy |
| Borrow | Agent Plugins package for Cursor distribution | Same package as Codex |
| Borrow | `agent -p` in the eval runner | Headless, honors deny rules |
| Skip | `.cursor-plugin/plugin.json` unless JDAD needs Cursor-only rules or hooks in a plugin | Agent Plugins covers skills and MCP |
| Skip | Team marketplace | Needs a Teams plan; not needed for one user |

## Unverified

- Whether `cursor-agent` still works as an alias for `agent`. Older docs and scripts use `cursor-agent`; the current docs use `agent`.
