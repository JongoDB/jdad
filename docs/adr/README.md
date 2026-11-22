# Architecture decision records

One file per decision: `NNNN-short-title.md`, numbered in order and never renumbered. Status is Proposed, Accepted, or Superseded by NNNN. Copy [0000-template.md](0000-template.md) to start one.

| ADR | Title | Status |
| --- | --- | --- |
| [0001](0001-canonical-skill-format-and-compilers.md) | Canonical skill format (Agent Skills spec) plus per-tool compilers | Proposed |
| [0002](0002-markdown-first-kb-git-as-database.md) | Markdown-first knowledge base with git as the database | Accepted |
| [0003](0003-stdio-plus-hosted-http-mcp.md) | One read-only MCP server: stdio locally, streamable HTTP when hosted (what's on `main` at 2022a8a) | Accepted |
| [0004](0004-agents-md-canonical-instructions.md) | AGENTS.md is the canonical instructions file; CLAUDE.md imports it | Proposed |
| [0005](0005-hosted-deploy-cloudflare-full-strict.md) | Hosted deploy: Docker on the droplet behind Cloudflare Full (strict) | Proposed (PR #2 merged (2022a8a); Accepted when P0.5 passes) |

An ADR may be Accepted only when what it decides is on `main`. Designs that are still in an open PR, or merged but not yet proven where proof is required, stay Proposed; `tests/test_docs.py` checks that Accepted ADRs only name files that exist and hostnames that `main`'s `.mcp.json` uses.
