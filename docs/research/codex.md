# OpenAI Codex CLI

Date checked: 2026-11-22. Source: the official docs at developers.openai.com/codex (markdown versions, `<page>.md`; some pages now link to learn.chatgpt.com).

## AGENTS.md

Source: https://developers.openai.com/codex/guides/agents-md

- Discovery: global `~/.codex/AGENTS.override.md` or `AGENTS.md` (first non-empty wins), then every directory from the project root down to the working directory, checking `AGENTS.override.md` then `AGENTS.md` (plus configured fallback names).
- "Codex concatenates files from the root down ... Files closer to your current directory override earlier guidance."
- Stops adding files once the combined size reaches `project_doc_max_bytes` (32 KiB by default).
- Read once per run, so edits apply to the next session.

## config.toml, sandbox, approvals

Sources: https://developers.openai.com/codex/config-basic, https://developers.openai.com/codex/config-reference, https://developers.openai.com/codex/config-advanced

- User config `~/.codex/config.toml`; project `.codex/` layers load only for trusted projects. Admins can pin limits in `requirements.toml` (for example, disallowing `approval_policy = "never"` or `sandbox_mode = "danger-full-access"`).
- `approval_policy` (for example `on-request`, `never`) and `sandbox_mode` (`read-only`, `workspace-write`, `danger-full-access`). Named permission profiles `:read-only`, `:workspace`, `:danger-full-access`, plus custom `[permissions.<name>]`.
- Workspace-write still protects `.git`, `.agents`, `.codex` and `.aws` paths.

## MCP

Source: https://developers.openai.com/codex/mcp

- `[mcp_servers.<name>]` tables. stdio (`command`, `args`, `env`) or streamable HTTP (`url`).
- HTTP auth: `bearer_token_env_var` (env var name for `Authorization: Bearer`), `http_headers`, `env_http_headers` (header → env var), `http_headers_helper`, or OAuth via `codex mcp add <name> --url ... --oauth-client-id ...`.

## Skills (replacing custom prompts)

Sources: https://developers.openai.com/codex/skills, https://developers.openai.com/codex/custom-prompts

- "Skills build on the open agent skills standard" (https://agentskills.io). `SKILL.md` must include `name` and `description`; optional `scripts/`, `references/`, `assets/`, and `agents/openai.yaml` for appearance and dependencies.
- Locations: `.agents/skills` in every directory from the working directory up to the repo root, then `$HOME/.agents/skills`, admin and system locations.
- Progressive disclosure: the initial skill list uses at most 2% of the context window (or 8,000 characters); descriptions are shortened first when many skills are installed. "Front-load the key use case and trigger words."
- Invocation: `$skill-name` or `/skills` explicitly, or implicit match on `description`. `$skill-creator` drafts one.
- "Custom prompts are deprecated. Use skills."

## Plugins and marketplaces

Sources: https://developers.openai.com/codex/plugins (installing and browsing plugins in Codex), https://developers.openai.com/plugins/build/plugins (packaging; the quotes below are from this page)

- "For a portable Agent Plugins package, add `plugin.json` at the plugin root and declare the Agent Plugins schema." OpenAI-specific settings go under `extensions.com.openai`. "Existing `.codex-plugin/plugin.json` files remain supported as a compatibility fallback."
- Marketplace: `$REPO_ROOT/.agents/plugins/marketplace.json` (repo) or `~/.agents/plugins/marketplace.json` (personal); entries point `source.path` at plugin folders. `codex plugin marketplace add <owner/repo>` adds a remote one (seen in wshobson/agents' README).

## Hooks and subagents

Sources: https://developers.openai.com/codex/hooks, https://developers.openai.com/codex/subagents

- Hooks: `hooks.json` at system, `$CODEX_HOME`, or trusted-project `.codex/hooks.json`, or `[hooks]` in `config.toml`. Events include `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`, `PostCompact`, `SubagentStart`, `SubagentStop`, `Stop`. Hooks need review and trust.
- Custom subagents are standalone TOML files in `~/.codex/agents/` or `.codex/agents/`.

## Non-interactive

Source: https://developers.openai.com/codex/noninteractive

- `codex exec "<prompt>"` streams progress to stderr and prints only the final message to stdout. `--ephemeral` avoids persisting the session.

## Borrow / skip

| Call | What | Why |
| --- | --- | --- |
| Borrow | `AGENTS.md` as the canonical instructions file, kept well under 32 KiB | Codex's instruction chain is `AGENTS.override.md` / `AGENTS.md` plus any fallback names you configure; it doesn't read `CLAUDE.md` by default. 32 KiB is the default `project_doc_max_bytes`, which can be changed, so staying under it keeps the default working |
| Borrow | Ship skills to `.agents/skills/` | Read by Codex, Cursor, and (user-level) Grok Build |
| Borrow | `bearer_token_env_var = "JDAD_TOKEN"` in the Codex MCP template | Keeps the token out of config files |
| Borrow | `sandbox_mode = "workspace-write"`, `approval_policy = "on-request"` as the template default | Least privilege that still lets the agent run `./verify` |
| Borrow | Agent Plugins root `plugin.json` for a Codex distribution | Same package can serve Cursor too |
| Borrow | `codex exec` in the eval runner | Clean stdout for graders |
| Skip | Custom prompts (`~/.codex/prompts`) | Deprecated in favor of skills |
| Skip | `danger-full-access` in any template | No need for it in the golden path |

## Unverified

- The exact `codex plugin` CLI subcommands beyond `marketplace add` and `add` (seen in a third-party README, not on the docs pages read).
- Whether Codex reads a Claude Code `.claude-plugin/marketplace.json` directly. wshobson/agents installs from a Claude-style repo with `codex plugin marketplace add`, which suggests it does, but the docs pages read do not say so.
