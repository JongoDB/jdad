# xAI Grok Build

Date checked: 2026-11-22. Sources: the official docs at docs.x.ai/build (pages say "SpaceXSI Docs"; read through https://docs.x.ai/llms-full.txt), the open-source repo https://github.com/xai-org/grok-build (Apache-2.0), and the official marketplace https://github.com/xai-org/plugin-marketplace.

## What it is

Confirmed. Grok Build is xAI's terminal coding agent (`grok`). It runs as a full-screen TUI, headless (`grok -p`), or as an Agent Client Protocol (ACP) agent (`grok agent stdio`). Install: `curl -fsSL https://x.ai/cli/install.sh | bash`. Overview: https://docs.x.ai/build/overview. The Verge covered the early beta: https://www.theverge.com/ai-artificial-intelligence/930802/xai-launches-an-early-beta-of-its-agentic-cli-for-grok

`grok inspect [--json]` shows "the configuration Grok discovers for this directory: rules, skills, plugins, hooks, and MCP servers". That makes it a cheap conformance check for JDAD's harness templates.

## Instructions (project rules)

Source: https://docs.x.ai/build/features/project-rules

- Loads global rules in `~/.grok/`, then every directory from the repo root to the working directory. "Within each directory, Grok reads any of `AGENTS.md`, `Agents.md`, `AGENT.md`, `CLAUDE.md`, `Claude.md`, and `CLAUDE.local.md`, plus every `*.md` file in a `.grok/rules/` directory (`.claude/rules/` and `.cursor/rules/` are read for compatibility)."
- Gitignored files are skipped. The repo's user guide (https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/12-project-rules.md) says Grok "loads every matching file in a directory, so a folder that contains both `AGENTS.md` and `CLAUDE.md` contributes both."
- "Files are loaded in full, with no size cap; short, specific instructions are followed more reliably than long ones."
- `--rules "<text>"` appends to the system prompt for one run.

## Skills, plugins, marketplaces

Source: https://docs.x.ai/build/features/skills-plugins-marketplaces

- Skills: `./.grok/skills/` (walked up to the repo root), `~/.grok/skills/`, enabled plugins' `skills/`, extra `[skills] paths`, plus `~/.agents/skills/` and `~/.agents/commands/`. Frontmatter: `name`, `description`, `when-to-use`, `paths`, `allowed-tools` (accepted, "does not grant or restrict tools"), `argument-hint`, `user-invocable`, `disable-model-invocation`, `metadata`. Extra keys are ignored.
- Plugins: skills, agents, hooks, MCP servers, LSP servers. Loaded from `./.grok/plugins/`, `~/.grok/plugins/`, marketplace installs, `--plugin-dir`.
- "Grok is fully compatible with Claude Code with zero configuration needed. Grok automatically reads Claude Code marketplaces, plugins, skills, MCPs, agents, hooks, and instruction files."
- Marketplace sources: `[[marketplace.sources]]` in `~/.grok/config.toml` and `~/.grok/plugins/known_marketplaces.json`. CLI: `grok plugin <list|install|uninstall|update|enable|disable|details|validate>` and `grok plugin marketplace <list|add|remove|update>`.
- The official marketplace repo uses `.grok-plugin/marketplace.json` (catalog with `name`, `owner`, `plugins[]`, URL sources pinned by `sha`). Superpowers' README (https://github.com/obra/superpowers) gives the install command `grok plugin install superpowers@xai-official --trust`; the Grok docs page doesn't show that exact command.

## Hooks

Source: https://docs.x.ai/build/features/hooks

- JSON files in `~/.grok/hooks/*.json` and `<project>/.grok/hooks/*.json`. Claude Code `.claude/settings.json` and Cursor `.cursor/hooks.json` hooks are read too, and Claude tool names map automatically.
- Events: `SessionStart`, `SessionEnd`, `UserPromptSubmit`, `PreToolUse` ("the only blocking event"), `PostToolUse`, `PostToolUseFailure`, `PermissionDenied`, `Stop`, `StopFailure`, `Notification`, `SubagentStart`, `SubagentStop`, `PreCompact`, `PostCompact`.
- Fail-open: "Everything else — timeouts, crashes, malformed output — is fail-open." Project hooks need trust (`/hooks-trust` or `--trust`).

## MCP

Source: https://docs.x.ai/build/features/mcp-servers

- `grok mcp add <name> -- <cmd>` (stdio) or `grok mcp add --transport http <name> <url> --header "Authorization: Bearer ${API_TOKEN}"`. `grok mcp doctor` diagnoses.
- `[mcp_servers.<name>]` in `~/.grok/config.toml` or project `.grok/config.toml` (`--scope project`). `${VAR}` and `${VAR:-default}` expand in `url`, `command`, `args`, `env`, `headers`.
- "Grok also loads MCP configurations from `~/.claude.json`, `.cursor/mcp.json`, and project `.mcp.json` files, merged below `config.toml` in priority."

## Permissions, sandbox, plan mode, subagents

Sources: https://docs.x.ai/build/features/permissions, https://docs.x.ai/build/features/sandbox, https://docs.x.ai/build/features/plan-mode, https://docs.x.ai/build/features/subagents

- Modes: Ask (default), Auto (classifier), Always-approve. `[permission] rules` with allow/deny per tool and pattern (permissions page). The precedence rule, merged across files with `deny` > `ask` > `allow`, is in the repo user guide (https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/05-configuration.md) and https://docs.x.ai/llms-full.txt, not on the permissions page.
- Sandbox is off by default; profiles `workspace`, `devbox`, `read-only`, `strict` (Landlock on Linux, Seatbelt on macOS). Built-ins do not protect `~/.ssh`; add a custom deny list.
- Plan mode drafts a plan for approval before edits; "Auto and always-approve do not skip this review."
- Subagents: built-in `general-purpose`, `explore`, `plan`; custom types in `.grok/agents/`.

## Headless

Source: https://docs.x.ai/build/cli/headless-scripting

- `grok -p "<prompt>" --output-format plain|json|streaming-json`, `--always-approve`, `--cwd`, `-m <model>`. Use `--no-auto-update` in CI. `XAI_API_KEY` for auth.

## Borrow / skip

| Call | What | Why |
| --- | --- | --- |
| Borrow | Rely on Grok's Claude compatibility for v1 distribution: the existing JDAD Claude marketplace should install as-is | Zero extra artifacts. Must be proven with `grok inspect` (roadmap P7.4) |
| Borrow | `grok inspect --json` as a template conformance test | Machine-readable proof of what loaded |
| Borrow | `.grok/config.toml` with `[mcp_servers.jdad]` and a `${JDAD_TOKEN}` header as a fallback template | Documented and explicit |
| Borrow | `grok -p --output-format json --no-auto-update` in the eval runner | Deterministic CI behavior |
| Watch | Grok loads **both** `AGENTS.md` and `CLAUDE.md` | If `CLAUDE.md` duplicates `AGENTS.md`, Grok sees the content twice. JDAD templates keep `CLAUDE.md` to an `@AGENTS.md` import plus Claude-only notes |
| Watch | Hooks fail open | Hooks are guardrails, not security boundaries; CI and deny rules stay the backstop |
| Skip | A separate `.grok-plugin/marketplace.json` for now | Only needed if the Claude marketplace doesn't load cleanly |

## Unverified

- Not tested live: whether `grok plugin marketplace add JongoDB/jdad` installs the JDAD Claude plugin and connects its HTTP MCP server with the bearer header.
- Whether Grok expands Claude's `@path` import syntax inside `CLAUDE.md`. The docs do not say. If it doesn't, Grok still reads `AGENTS.md` directly, so nothing is lost.
- Whether Grok supports the Agent Plugins root `plugin.json` standard. Not mentioned in the docs read.
