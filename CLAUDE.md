# Working in this repository

@AGENTS.md

`AGENTS.md` (imported above) holds the rules for every agent in this repo, by ID. This file adds only what is specific to Claude Code and the JDAD plugin; never restate an `AGENTS.md` rule here.

## Claude-only

- **R-cc-1** The plugin `.mcp.json` sends `Authorization: Bearer ${JDAD_TOKEN}` only, to `https://jdad-mcp.jondevs.com/mcp` (Claude Code expands `${JDAD_TOKEN}` from the environment). Don't add `CF-Access-*` headers to the default config: unset variables are sent as the literal `${...}` text. Those headers are an optional documented variant if Cloudflare Access is used later.
- **R-cc-2** `/jdad add <url>` must not write an entry. It only tells the user to send the URL to Daisy.
- **R-cc-3** The `/jdad` command lives in `commands/jdad.md`; don't split it into four command files.
- **R-cc-4** `claude plugin validate .` must pass. `./verify` runs it when the `claude` CLI is on `PATH`.
