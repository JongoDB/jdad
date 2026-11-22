# 0002: Markdown-first knowledge base with git as the database

- Status: Accepted (records the design in place since d104c73 and PR #1)
- Date: 2026-11-22
- Deciders: Jon, roadmap author

## Context

The KB is written by agents (Daisy ingests videos and articles), read by agents through MCP and skills, and reviewed by Checker and Jon in PRs. OpenAI's harness-engineering post argues for "repository knowledge as the system of record" with mechanical checks on docs; Anthropic's harness posts hand off state through files and git history.

## Decision

1. The KB is plain Markdown in git: `sources/` is the verbatim record of each source; `practices/` is the tagged, cited advice. No database server.
2. Every change goes through a PR with `./verify` and independent review. Git history is the audit log; `kb_version` reports the SHA and newest entry date.
3. Structure is enforced by lint (rule IDs, tags, citations, source frontmatter; roadmap P1.2, P1.3), not by a schema engine.
4. Derived data (search index, embeddings, stats) is built from the Markdown at deploy or update time and never edited by hand.
5. The MCP server stays read-only over this tree.

## Consequences

- Humans and agents can read, diff and review every entry; rollback is `git revert`.
- Search quality depends on indexing the Markdown well (P3.1, P3.2).
- Concurrent edits to one practice file can conflict; keep topic files focused and PRs small.

## Alternatives considered

- **SQLite or Postgres as the store**: better queries, but opaque in review and needs migrations. Rejected; can be added later as a derived index.
- **A vector database as the store**: loses citations and reviewability. Rejected as a primary store; allowed as a derived index (P3.2).
