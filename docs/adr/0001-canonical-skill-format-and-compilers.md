# 0001: Canonical skill format (Agent Skills spec) plus per-tool compilers

- Status: Proposed (approved by Jon 2026-11-22; Accepted once P1.4 and P1.5 land on `main`)
- Date: 2026-11-22
- Deciders: Jon (approve), roadmap author

## Context

JDAD must ship the same skills and rules to Claude Code, Codex, Grok Build and Cursor. Research ([docs/research/](../research/README.md)) found:

- All four tools load `SKILL.md` skills that follow, or are compatible with, the Agent Skills spec (https://agentskills.io/specification). Claude Code and Codex say so outright; Cursor is a listed client; Grok Build documents compatible frontmatter and ignores extra keys.
- Locations differ: Claude Code reads `.claude/skills/` and plugin `skills/`; Codex reads `.agents/skills/`; Cursor reads `.agents/skills/`, `.cursor/skills/`, and also `.claude/skills/` and `.codex/skills/`; Grok Build reads `.grok/skills/`, `~/.agents/skills/`, and Claude skills and plugins.
- Extras differ: Claude Code adds `disable-model-invocation`, `context: fork`, `paths`, `argument-hint` and more. claude.ai and the Skills API reject anything outside the six spec fields.
- Cursor rules (`.mdc` with `globs`, `alwaysApply`) do something skills don't: file-glob scoping for always-on rules.
- wshobson/agents and obra/superpowers already feed many harnesses from one tree.

## Decision

1. The source of truth is `catalog/skills/<name>/SKILL.md` using **only** the six Agent Skills spec fields at the top level. Tool-specific options live under `metadata` with a tool prefix (for example `metadata: {claude.disable-model-invocation: "true"}`).
2. Always-on, file-scoped guidance lives in `catalog/rules/<name>.md` with `description`, `globs` and `always` fields.
3. `jdad build` compiles the catalog to each target: Claude plugin `skills/` (with Claude extras lifted out of `metadata`), an `.agents/skills/` tree, Cursor `.mdc` rules, and later an Agent Plugins package. Generated files carry a "generated, do not edit" header.
4. `./verify` runs the spec validator and `jdad build --check`, so stale or invalid output fails.

## Consequences

- One edit per skill; drift between tools becomes a failing check.
- The compiler is code JDAD must maintain and test with golden files.
- Generated files are committed (plugins install from git), so diffs show both source and output.
- Skills stay portable to claude.ai and the Skills API.

## Alternatives considered

- **Hand-maintained copies per tool**: rejected; guaranteed drift.
- **Claude Code format as the source, with others reading Claude dirs**: Cursor and Grok Build read Claude skills, but Codex reads `.agents/skills/`, and Claude-only frontmatter breaks claude.ai uploads. Workable as a v0 fallback, not the canonical form.
- **Symlinks instead of a compiler**: cheap, but can't transform frontmatter or produce `.mdc` rules, and symlinks are unreliable on Windows checkouts.
