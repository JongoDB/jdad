# 0004: AGENTS.md is the canonical instructions file; CLAUDE.md imports it

- Status: Proposed (approved by Jon 2026-11-22; Accepted once roadmap P1.1 lands on `main`)
- Date: 2026-11-22
- Deciders: Jon (approve), roadmap author

## Context

- Codex reads `AGENTS.override.md` / `AGENTS.md` plus any configured fallback filenames, not `CLAUDE.md` by default; the combined size default (`project_doc_max_bytes`) is 32 KiB and is configurable. Cursor reads `AGENTS.md` or `.cursor/rules`. Grok Build reads `AGENTS.md` **and** `CLAUDE.md`, loading every match.
- Claude Code reads `AGENTS.md` only when there is no `CLAUDE.md`, but a `CLAUDE.md` that imports `@AGENTS.md` gets both.
- OpenAI's harness post: a ~100-line `AGENTS.md` as a table of contents beats one giant manual. Claude's docs: keep `CLAUDE.md` under 200 lines. JDAD's single target: `AGENTS.md` at most 120 lines and under 32 KiB, enforced by `tests/test_docs.py`.

## Decision

1. `AGENTS.md` holds the repo's instructions for every tool: a short map, the verify command, the workflow, and pointers into `docs/`.
2. `CLAUDE.md` is `@AGENTS.md` plus Claude-only notes. It never restates `AGENTS.md` content, because Grok Build loads both files.
3. JDAD's harness templates follow the same pattern.

## Consequences

- One file to maintain; every tool gets the same rules.
- Grok Build may see the `@AGENTS.md` line as plain text if it doesn't expand imports (unverified). Harmless, since it reads `AGENTS.md` directly.
- In this repo, the migration waits for PR #2 to merge, because both edit `CLAUDE.md`. Until then `AGENTS.md` carries the workflow and points to `CLAUDE.md` for the existing rules.

## Alternatives considered

- **`CLAUDE.md` canonical, symlink `AGENTS.md` to it**: Grok Build could load the same text twice, and Claude-only notes would leak to other tools.
- **Separate full files per tool**: drift.
