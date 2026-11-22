# AGENTS.md

JDAD (Jon-does-agentic-dev) is an opinionated knowledge base, MCP server, skills catalog and harness for coding agents building production software. This file is the map for any agent working in this repo (Claude Code, Codex, Grok Build, Cursor).

## Read in this order

1. [docs/VISION.md](docs/VISION.md): principles, the golden path, what's opinionated vs configurable.
2. [ROADMAP.md](ROADMAP.md): the work queue. Pick the first unchecked item whose dependencies are done and that isn't waiting on Jon.
3. [CLAUDE.md](CLAUDE.md): the current repo rules (KB entries, MCP server, versioning, what not to do). They apply to every tool, not only Claude Code, until roadmap item P1.1 moves them here.
4. As needed: [docs/adr/](docs/adr/README.md) for decisions, [docs/research/](docs/research/README.md) for the sources behind them.

## Workflow

1. **One roadmap item per session.** Don't start a second item in the same branch.
2. **Plan first.** Find or create the item's Linear card (workspace `jongodb`, team `JON`, project `JDAD`) and post a plan before coding: steps, risks, and how you will verify each acceptance criterion.
3. **Branch** from `main` (`feat/…`, `fix/…`, `docs/…`). Never push to `main`.
4. **Build in small commits.** Add or update tests with the change. Never weaken or delete a test to make it pass.
5. **Verify.** Run `./verify` and keep the output. It must end with `verify: ok`.
6. **Open a PR** that links the card and includes: what changed and why, evidence (commands and output), and an **Unverified** list (anything you couldn't run or confirm). Tick the roadmap item in the same PR.
7. **Review.** Checker (Jon's verification bot) or another agent with fresh context reviews the PR. Don't merge your own PR; Jon approves merges.
8. **Learn.** If a reviewer catches something an agent should have known, add it to the instructions file or, once roadmap P1.6 lands, to `LESSONS.md`.

## Commands

- `./verify`: the full check (versions, deploy scripts, ruff, pytest, build, plugin validate when the `claude` CLI is present).
- `uv run pytest`: tests only.
- `uv run jdad-mcp` (stdio) or `uv run jdad-mcp --http` (streamable HTTP on `127.0.0.1:8765`).

## Hard rules

- The MCP server is read-only and offline: no writes to `practices/` or `sources/`, no outbound network, no model calls.
- No secrets, tokens or keys anywhere in the repo.
- KB rules cite a source or are labeled a KB addition.
- Version fields move in lockstep (see CLAUDE.md); `./verify` checks it.
