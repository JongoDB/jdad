# Claude Code

Date checked: 2026-11-22. Source: the official docs at code.claude.com (markdown versions, `<page>.md`).

## Memory: CLAUDE.md, rules, AGENTS.md

Sources: https://code.claude.com/docs/en/memory, https://code.claude.com/docs/en/best-practices

- Load order, broadest first: managed policy (`/etc/claude-code/CLAUDE.md` on Linux), user (`~/.claude/CLAUDE.md`), project (`./CLAUDE.md` or `./.claude/CLAUDE.md`), local (`./CLAUDE.local.md`, gitignored). Files above the working directory load at launch; files in subdirectories load on demand.
- `@path` imports expand into context, relative to the importing file, up to four hops deep. Imports organize a file but "don't reduce its context cost."
- `.claude/rules/` holds topic files; a rule with `paths:` frontmatter loads only when Claude touches matching files.
- Size: "target under 200 lines per CLAUDE.md file. Longer files consume more context and reduce adherence."
- Project-root CLAUDE.md is re-read from disk after `/compact`; conversation-only instructions are lost.
- AGENTS.md: "By default, Claude reads `AGENTS.md` only when you have no `CLAUDE.md` in your working directory or above it." A `CLAUDE.md` that imports `AGENTS.md` gets both. A `claude-md-and-agents-md` setting loads both without an import. Direct AGENTS.md reading needs v2.1.277+.
- "Claude treats CLAUDE.md files and auto memory as context. They aren't enforced configuration. To block an action regardless of what Claude decides, use a PreToolUse hook instead."
- `/doctor prompt-audit` checks CLAUDE.md, AGENTS.md, rules, skills, commands, subagents and output styles for stale or conflicting content.
- Auto memory: Claude writes its own `MEMORY.md` per repo (first 200 lines or 25KB load).

## Skills and slash commands

Source: https://code.claude.com/docs/en/skills

- "Claude Code skills follow the Agent Skills open standard" (https://agentskills.io). Claude Code adds extensions: invocation control, `context: fork` subagent execution, dynamic context injection.
- "Custom commands have been merged into skills." `.claude/commands/*.md` still works; `.claude/skills/<name>/SKILL.md` is the same command with supporting files.
- Frontmatter: `name`, `description` (+ `when_to_use`; combined text truncated at 1,536 characters in the listing), `disable-model-invocation`, `allowed-tools`, `disallowed-tools`, `model`, `effort`, `context: fork`, `agent`, `paths`, `argument-hint`, plus spec fields `license`, `compatibility`, `metadata`.
- Outside Claude Code (claude.ai uploads, Skills API) only the six spec fields are accepted: `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`.
- Progressive disclosure: only name and description are always in context; the body loads on use. "Keep `SKILL.md` under 500 lines. Move detailed reference material to separate files."
- `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PLUGIN_ROOT}` substitutions let a skill run a bundled script with a matching `allowed-tools` rule.
- `claude plugin validate .claude/skills` finds unparseable frontmatter.

## Plugins and marketplaces

Sources: https://code.claude.com/docs/en/plugins, https://code.claude.com/docs/en/plugins-reference, https://code.claude.com/docs/en/plugins/host-marketplace.md, https://code.claude.com/docs/en/plugins/loading.md, https://code.claude.com/docs/en/plugin-evals.md

- A plugin bundles skills, agents, hooks, MCP servers, LSP servers and monitors. Manifest: `.claude-plugin/plugin.json` (only `name` is required). A marketplace is a repo with `.claude-plugin/marketplace.json`.
- "An enabled plugin is part of every session": every model-invocable skill's name and description costs tokens on every turn.
- `userConfig` in `plugin.json` prompts the user for values at enable time; `"sensitive": true` masks input and stores it in secure storage, not `settings.json`.
- `version` is "not checked against semver. Setting it pins the plugin to that version until you change it." Users get a new copy "only when its computed version changes."
- Background auto-update is **off** for third-party marketplaces by default, and `marketplace.json` has no field to turn it on. A user turns it on in `/plugin` → Marketplaces, or an admin sets it in managed settings.
- Private marketplaces use whatever git credentials the machine already has; `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1` is recommended in install instructions.
- `claude plugin eval` runs eval cases (prompt + graders) in fresh, isolated headless sessions with only the plugin loaded, compares against a no-plugin baseline, and can gate CI. `claude plugin eval init` drafts a suite.

## Subagents

Source: https://code.claude.com/docs/en/sub-agents

- Markdown files with frontmatter in `.claude/agents/` or a plugin's `agents/`. Fields include `name`, `description`, `tools`, `disallowedTools`, `model`, `permissionMode`, `maxTurns`, `skills` (preloaded), `mcpServers`, `hooks`, `memory`, `isolation: worktree`, `omitClaudeMd`.

## Hooks

Sources: https://code.claude.com/docs/en/hooks, https://code.claude.com/docs/en/hooks-guide

- 30+ events, including `SessionStart`, `UserPromptSubmit`, `PreToolUse` (can block), `PermissionRequest`, `PostToolUse`, `Stop`, `SubagentStop`, `PreCompact`, `InstructionsLoaded`, `ConfigChange`, `WorktreeCreate`, `SessionEnd`.
- Exit code 2 blocks. A `Stop` hook that exits 2 sends Claude back to work with stderr as the reason. After eight blocked stops in a row with no tool call between them, Claude Code overrides the block.

## Best practices page (the harness view)

Source: https://code.claude.com/docs/en/best-practices

- Every instruction is either non-deterministic (prompt, CLAUDE.md, skill: "Claude decides") or deterministic (hook, deny rule, managed setting, CI: "Claude Code enforces").
- "If you keep adding emphasis to a `CLAUDE.md` line and Claude still misses it, that's a sign the line belongs in a hook. The reverse holds too."
- "Give Claude something it can run that comes back pass or fail." "If your repo already has one of these, the single most useful line in your `CLAUDE.md` is the command that runs it."
- Review by "someone who didn't write the code": `/code-review` runs in a fresh subagent. For spec reviews: "report gaps that affect correctness and skip style." "Don't drop the `skip style` part ... A reviewer that's asked to find problems will always find *something*."
- Ask for evidence: "the command it ran and its output."

## Output styles

Source: https://code.claude.com/docs/en/output-styles

- Session-wide instructions about how Claude responds. The docs steer project knowledge to CLAUDE.md and must-happen behavior to hooks.

## Settings and permissions

Sources: https://code.claude.com/docs/en/settings, https://code.claude.com/docs/en/permissions

- Precedence, highest first: managed, command line, project local (`.claude/settings.local.json`), shared project (`.claude/settings.json`), user.
- Permission modes: `default` (manual), `acceptEdits`, `plan`, `auto` (classifier), `dontAsk`, `bypassPermissions`. Allow/ask/deny rules per tool and pattern; deny wins.

## MCP

Source: https://code.claude.com/docs/en/mcp

- Scopes: local, project (`.mcp.json`, committed, needs per-user approval), user. `type: "http"` (alias `streamable-http`). `${VAR}` expansion in config.
- MCP tool search keeps large tool sets out of context until needed.

## Headless and SDK

Sources: https://code.claude.com/docs/en/headless, https://code.claude.com/docs/en/agent-sdk/overview

- `claude -p "<prompt>" --allowedTools ... --output-format json`. "`--bare` is the recommended mode for scripted and SDK calls" and skips hooks, skills, plugins, MCP, memory and CLAUDE.md discovery. Without `--bare`, `-p` runs a project's hooks and MCP servers "even in a folder you've never trusted."
- In bare mode "Claude Code never reads OAuth credentials or the system keychain": set `ANTHROPIC_API_KEY` (or an `apiKeyHelper`). Bare mode also skips hooks, skills, plugins, MCP servers, memory and CLAUDE.md unless they're passed explicitly, which matters for evals (ROADMAP P6.2).
- `--max-turns` and `--max-budget-usd` bound a scripted run (from https://code.claude.com/docs/en/best-practices, not the headless page).

## Borrow / skip

| Call | What | Why |
| --- | --- | --- |
| Borrow | Keep `CLAUDE.md` short (<200 lines) and make it import `AGENTS.md` | Cross-tool single source; Claude ignores `AGENTS.md` when a `CLAUDE.md` exists |
| Borrow | Skills for procedures, `.claude/rules/` with `paths:` for area rules, CLAUDE.md for facts | Matches the docs' own split and keeps always-on context small |
| Borrow | `Stop` hook that runs a fast `./verify` subset in templates | Turns "run the tests" into an enforced loop |
| Borrow | Deny rules for secrets and destructive commands in template `settings.json` | Deterministic floor for things that must never happen |
| Borrow | `userConfig` with `sensitive: true` for `JDAD_TOKEN` | Replaces "export an env var" with a prompted, masked secret |
| Borrow | `claude plugin eval` for skill-trigger and outcome evals | Ships with the tool; supports a no-plugin baseline |
| Borrow | `claude -p --bare` in the eval runner | Reproducible, no ambient config |
| Skip | Output styles in the default harness | Per-user taste, not a project standard |
| Skip | Turning every rule into a hook | The docs warn that preference hooks should be deleted |

## Unverified

- Whether Claude Code loads an Agent Plugins root `plugin.json` (the plugin-evals page accepts "a `plugin.json` or `.claude-plugin/plugin.json` manifest", but the plugins reference only documents `.claude-plugin/`).
