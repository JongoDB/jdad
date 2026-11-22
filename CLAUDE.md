# Working in this repository

Start with @AGENTS.md: it sets the reading order (docs/VISION.md, then ROADMAP.md, then this file) and the workflow (one roadmap item per session, plan on the Linear card first, `./verify`, PR for Checker review). The rules below apply to every agent until roadmap item P1.1 moves them into AGENTS.md.

This repo is JDAD (Jon-does-agentic-dev), Jon's agentic coding knowledge base. The MCP server in `src/jdad/` is how other coding agents (Claude Code, Codex, cursor-agent) read it. It is read-only at runtime: never add a tool, resource, or code path that writes to `practices/` or `sources/`.

The package and CLI are named `jdad`. The entry point is `jdad-mcp`. It serves stdio by default and streamable HTTP with `jdad-mcp --http` (default bind `127.0.0.1:8765`). A non-loopback bind without `JDAD_TOKEN` is refused unless `--allow-no-auth` is passed.

## Adding a knowledge-base entry

When Jon (or anyone) sends a video, article, or thread to mine:

1. Watch or read the source yourself. Do not invent points that are not in it.
2. Create `sources/YYYY-MM-DD-<slug>.md`. Include:
   - Title and author/account
   - Link
   - Date posted or retrieved, and a short note on the format (reel, talk, post, docs)
   - What is useful and what is missing
   - A verbatim (or as-close-as-possible) record of the extractable practices
3. Fold the useful rules into `practices/<topic>.md`, or add a new topic file if none fits.
   - Deduplicate. If a rule already exists, add a source citation instead of repeating the bullet.
   - Tag every section with one or more of: `[frontend]` `[backend]` `[db]` `[infra]` `[observability]` `[testing]`.
   - Cite the source on each rule, e.g. `(src: breakingbreach #8)`.
   - Add an "applies when" note when a rule is easy to over-apply.
   - If you add a rule that did not come from the source, label it clearly as a KB addition (see Rule zero in `practices/performance.md`).
4. One skill per `practices/` topic file. If you created `practices/<topic>.md`, add `skills/jdad-<topic>/SKILL.md` with a description that will auto-trigger, and put the rules (or a pointer to `get_practice`) in the body. The `/jdad` command lives in `commands/jdad.md`; do not split it into four command files.
5. Bump the version in lockstep: `pyproject.toml`, `src/jdad/__init__.py`, `uv.lock`, `.claude-plugin/plugin.json`, and the plugin entry in `.claude-plugin/marketplace.json` (patch for a new source or rule, minor if you add a topic or tool). `./verify` fails if they differ.
6. Do not put secrets, tokens, keys, or credentials anywhere in this repo. The token belongs on the host: `~/.config/jdad/token` (mode 0400) for the Docker deploy, `/etc/jdad.env` for the legacy systemd layout.
7. Run `uv run pytest` and make sure the new topic or source is reachable through the MCP tools (`list_topics` / `list_sources`, a search or checklist that hits the new rules, and `kb_version` showing the new entry date when the filename is dated).

`/jdad add <url>` must not write an entry. It only tells the user to send the URL to Daisy.

## Changing the MCP server

- Stack: official `mcp` Python SDK v2 (`MCPServer`, the successor to `FastMCP`), stdio entry point `jdad-mcp`, HTTP via `--http`.
- Keep it dependency-light and offline. No network calls from the server.
- Practice files must stay available as `kb://practices/<name>` resources.
- Keep the `apply-kb` prompt, `kb_version` (git SHA plus newest entry date; git is invoked with `--no-optional-locks`), `/healthz` (`{"status": "ok"}` only), and optional bearer auth from `JDAD_TOKEN`. The plugin `.mcp.json` must send `Authorization: Bearer ${JDAD_TOKEN}` only, with URL `https://jdad-mcp.jondevs.com/mcp` (Claude Code expands `${JDAD_TOKEN}` from the environment). Do not add `CF-Access-*` headers to the default config; unset vars are sent as the literal `${...}` text. Those headers are an optional documented variant if Access is used later.
- Tests in `tests/` start the server in-process (`mcp.Client(mcp)`), over stdio (`uv run jdad-mcp`), and over HTTP (`create_http_app()`). Update them when you add a tool. Run `./verify` before you push.

## What not to do

- Do not rewrite a `sources/` file to match a cleaned-up practice. The source file is the record of the source; the practice file is the advice.
- Do not merge this repo's practices into a project's `CLAUDE.md` from here automatically. Other repos should query the MCP server (or copy a checklist) themselves.
