# AGENTS.md

JDAD (Jon-does-agentic-dev) is an opinionated knowledge base, MCP server, skills catalog and harness for coding agents building production software. This is the canonical instructions file for every agent working in this repo (Claude Code, Codex, Grok Build, Cursor). `CLAUDE.md` imports it and adds only Claude Code notes ([ADR 0004](docs/adr/0004-agents-md-canonical-instructions.md)).

## Read in this order

1. [docs/VISION.md](docs/VISION.md): principles, the golden path, what's opinionated vs configurable.
2. [ROADMAP.md](ROADMAP.md): the work queue. Take the first unchecked item in its Current order whose dependencies are done and that isn't waiting on Jon.
3. The rules below, then [LESSONS.md](LESSONS.md): what reviewers caught before. Claude Code also loads the Claude-only notes in [CLAUDE.md](CLAUDE.md).
4. As needed: [docs/adr/](docs/adr/README.md) for decisions, [docs/research/](docs/research/README.md) for the sources behind them.

## Commands

- `./verify`: the full check (versions, deploy scripts, Docker smoke test when Docker is up, ruff, pytest, build, `claude plugin validate` when the CLI is present). It must end `verify: ok`.
- `./verify --fast`: ruff and pytest only, in seconds. Run it before you say you're done (R-flow-8).
- `uv run pytest`: tests only.
- `uv run jdad-mcp` (stdio) or `uv run jdad-mcp --http` (streamable HTTP on `127.0.0.1:8765`).

## The server in brief

The package and CLI are named `jdad`; the entry point is `jdad-mcp`, which serves stdio by default and streamable HTTP with `--http`. A non-loopback bind without `JDAD_TOKEN` is refused unless `--allow-no-auth` is passed. The server in `src/jdad/` is how coding agents read the KB in `practices/` and `sources/`.

## Rules

Every normative rule has an ID. `tests/test_instructions.py` checks that each ID is defined exactly once: in this table, or (rows marked Claude-only) in the Claude-only section of `CLAUDE.md`.

| ID | Rule |
| --- | --- |
| R-flow-1 | One roadmap item per session, and one per branch. |
| R-flow-2 | Plan first: find or create the item's Linear card (workspace `jongodb`, team `JON`, project `JDAD`) and post the plan (steps, risks, how each acceptance criterion will be verified) before coding. |
| R-flow-3 | Branch from `main` (`feat/…`, `fix/…`, `docs/…`). Never push to `main`, never force-push, never merge your own PR; Jon approves merges. |
| R-flow-4 | Build in small commits and add or update tests with each change. Never weaken or delete a test to make it pass. |
| R-flow-5 | Run `./verify` and keep the output. It must end `verify: ok`, or the PR says exactly what didn't run. |
| R-flow-6 | The PR links the card and has "What changed and why", evidence (commands and output) and an **Unverified** list (anything you couldn't run or confirm). Tick the roadmap item in the same PR. |
| R-flow-7 | Checker (Jon's verification bot) or another agent with fresh context reviews every PR. When a reviewer catches something an agent should have known, add a dated entry with a link to `LESSONS.md`. |
| R-flow-8 | Before you say a task is done, run `./verify --fast` (ruff and pytest) and fix what fails. |
| R-kb-1 | To mine a video, article or thread, watch or read the source yourself. Don't invent points that aren't in it. |
| R-kb-2 | Record it in `sources/YYYY-MM-DD-<slug>.md`: title and author or account, link, date posted or retrieved, the format (reel, talk, post, docs), what is useful and what is missing, and a verbatim (or as close as possible) record of the extractable practices. |
| R-kb-3 | Fold the useful rules into `practices/<topic>.md`, or a new topic file if none fits. Deduplicate: if a rule already exists, add a source citation instead of repeating it. |
| R-kb-4 | Tag every practice section with one or more of `[frontend]` `[backend]` `[db]` `[infra]` `[observability]` `[testing]`. |
| R-kb-5 | Cite the source on each rule, e.g. `(src: breakingbreach #8)`. Label a rule that didn't come from a source as a KB addition (see Rule zero in `practices/performance.md`). Add an "applies when" note when a rule is easy to over-apply. |
| R-kb-6 | One skill per practice topic: a new `practices/<topic>.md` gets `catalog/skills/jdad-<topic>/SKILL.md` (the canonical copy, spec in `catalog/README.md`), with a description that will auto-trigger and the rules (or a pointer to `get_practice`) in the body. Copy it to `skills/` until `jdad build` (P1.5) generates that. |
| R-kb-7 | After a KB change, run `uv run pytest` and check the entry is reachable through the MCP tools: `list_topics` or `list_sources`, a search or checklist that hits the new rules, and `kb_version` showing the new entry date when the file name is dated. |
| R-kb-8 | Never rewrite a `sources/` file to match a cleaned-up practice. The source file is the record of the source; the practice file is the advice. |
| R-kb-9 | Never merge this repo's practices into another project's instructions file from here. Other repos query the MCP server, or copy a checklist, themselves. |
| R-ver-1 | Bump the version in lockstep in `pyproject.toml`, `src/jdad/__init__.py`, `uv.lock`, `.claude-plugin/plugin.json` and the plugin entry in `.claude-plugin/marketplace.json`: patch for a new source or rule, minor for a new topic or tool. `./verify` fails if they differ. |
| R-sec-1 | No secrets, tokens, keys or credentials anywhere in the repo. `JDAD_TOKEN` belongs on the host (`/etc/jdad.env`), not here. |
| R-sec-2 | Never read or write `.env*`, `*.pem` or `id_*` files, never run `rm` with both recursive and force flags, and never force-push (`--force`, `-f`, `--force-with-lease`, `+refspec`). |
| R-mcp-1 | The server is read-only and offline: no tool, resource or code path that writes to `practices/` or `sources/`, no outbound network, no model calls. Keep it dependency-light. |
| R-mcp-2 | Build on the official `mcp` Python SDK v2 (`MCPServer`, the successor to `FastMCP`), with the stdio entry point `jdad-mcp` and HTTP via `--http`. |
| R-mcp-3 | Practice files stay available as `kb://practices/<name>` resources. Keep the `apply-kb` prompt, `kb_version` (git SHA plus newest entry date; git runs with `--no-optional-locks`), `/healthz` (returns `{"status": "ok"}` only) and optional bearer auth from `JDAD_TOKEN`. |
| R-mcp-4 | Tests start the server in-process (`mcp.Client(mcp)`), over stdio (`uv run jdad-mcp`) and over HTTP (`create_http_app()`). Update them when you add a tool. |
| R-cc-1 | Claude-only: CLAUDE.md (the plugin's `.mcp.json` header). |
| R-cc-2 | Claude-only: CLAUDE.md (`/jdad add` writes nothing). |
| R-cc-3 | Claude-only: CLAUDE.md (one `/jdad` command file). |
| R-cc-4 | Claude-only: CLAUDE.md (`claude plugin validate`). |
| R-cc-5 | Claude-only: CLAUDE.md (the deny rules and hooks that enforce R-sec-2 and R-flow-8). |

## Changing these rules

Add a row with the next free number in its area; never renumber or reuse an ID. A rule only Claude Code needs goes in `CLAUDE.md`'s Claude-only section, with a pointer row here. Never restate a rule in both files: Grok Build loads both.
