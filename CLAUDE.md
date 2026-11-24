# Working in this repository

@AGENTS.md

`AGENTS.md` (imported above) holds the rules for every agent in this repo, by ID. This file adds only what is specific to Claude Code and the JDAD plugin; never restate an `AGENTS.md` rule here.

## Claude-only

- **R-cc-1** The plugin `.mcp.json` sends `Authorization: Bearer ${user_config.jdad_token}` only, to `https://jdad-mcp.jondevs.com/mcp`. The token is the plugin's `userConfig.jdad_token` option (`sensitive: true`, so Claude Code keeps it in the OS credential store, never in `settings.json`; roadmap P3.7). Other clients (Codex, Cursor, Grok Build) keep reading `JDAD_TOKEN` from the environment. Don't add `CF-Access-*` headers to the default config: unset variables are sent as the literal `${...}` text. Those headers are an optional documented variant if Cloudflare Access is used later.
- **R-cc-2** `/jdad add <url>` must not write an entry. It only tells the user to send the URL to Daisy.
- **R-cc-3** The `/jdad` command lives in `commands/jdad.md`; don't split it into four command files.
- **R-cc-4** `claude plugin validate .` must pass. `./verify` runs it when the `claude` CLI is on `PATH`.
- **R-cc-5** `.claude/settings.json` enforces R-sec-2 and R-flow-8: deny rules, a `PreToolUse` hook (`.claude/hooks/guard.py`) that denies the same things before a tool runs, and a `Stop` hook (`.claude/hooks/stop_verify.py`) that runs `./verify --fast` and blocks finishing (exit 2) while it fails, once per stop. Don't loosen them; `tests/test_harness.py` covers both hooks. Per-user overrides go in the git-ignored `.claude/settings.local.json`.
