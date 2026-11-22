# JDAD (Jon-does-agentic-dev)

Best practices pulled from videos and articles Jon sends, plus an MCP server and a Claude Code plugin that coding agents can use while they plan and build.

The MCP server is read-only. It never writes to the knowledge base and makes no network calls.

The hosted URL used in the plugin and in the agent configs below is a placeholder:

```
http://jdad.local:8765/mcp
```

Point it at the Ubuntu LXC once that host and DNS (or `/etc/hosts`) are in place. `/healthz` is the liveness probe on the same origin.

## Layout

```
practices/                 deduped rules, one topic per file, tagged by area
sources/                   one file per source: link, author, date, and a verbatim record
src/jdad/                  stdio + streamable HTTP MCP server (official `mcp` Python SDK)
deploy/                    systemd unit, env example, and an idempotent update script
.claude-plugin/            marketplace.json and plugin.json
.mcp.json                  plugin MCP config (points at the hosted URL)
commands/jdad.md           /jdad slash command
skills/jdad-performance/   one skill per practices topic file
tests/
```

- `sources/` is the archive. Each file belongs to one source and keeps what that source actually said, in its own words.
- `practices/` is what agents should follow. Rules are merged, tagged, and each one cites its source. When two sources disagree, keep both and say so; do not silently drop one.
- Tags: `[frontend]` `[backend]` `[db]` `[infra]` `[observability]` `[testing]`. Mark "applies when" on a rule so agents do not over-apply it.

The official Python MCP SDK v2 renamed `FastMCP` to `MCPServer`. This server uses `MCPServer`.

## Adding an entry

1. Add `sources/YYYY-MM-DD-<slug>.md` with the link, author, date, format, and a verbatim write-up of the useful points.
2. Fold new rules into `practices/<topic>.md`. Deduplicate against what is already there. Tag each section, and cite the source on each rule (for example `(src: breakingbreach #8)`).
3. If you add a new topic file under `practices/`, add a matching skill at `skills/jdad-<topic>/SKILL.md` (one skill per practice file). If you add a rule that did not come from the source, label it as a KB addition, the way Rule zero is labeled in `practices/performance.md`.
4. Bump the patch (or minor) version in `.claude-plugin/plugin.json` so Claude Code hosts get prompted to update. Keep `pyproject.toml` in sync when the server changes.
5. Do not put secrets, tokens, or credentials in this repo.

See [CLAUDE.md](CLAUDE.md) for the same instructions aimed at agents working in this repo.

## MCP server

Entry point: `jdad-mcp`.

```bash
# stdio, from a local clone
uv run jdad-mcp

# stdio, from git (needs git auth for this private repo)
uvx --from git+https://github.com/JongoDB/jdad jdad-mcp

# streamable HTTP, defaults to 127.0.0.1:8765
jdad-mcp --http

# on the LXC, listen on all interfaces (requires JDAD_TOKEN, or --allow-no-auth)
jdad-mcp --http --host 0.0.0.0 --port 8765
```

`KB_ROOT` overrides the content directory. It must point at a directory that contains `practices/` and `sources/`. If unset, the server uses a checkout of this repo when it can find one, otherwise the files bundled in the package.

`JDAD_TOKEN` is optional on loopback. When set, every HTTP path except `/healthz` requires `Authorization: Bearer <token>`. Stdio does not use the token. Store the value in `/etc/jdad.env` (mode 0600) on the host; never commit it.

The default HTTP bind is `127.0.0.1`. Binding to a non-loopback address (`0.0.0.0`, a public IP, or a hostname other than `localhost`) without `JDAD_TOKEN` refuses to start unless you pass `--allow-no-auth`, which logs a loud warning.

### Tools

| Tool | What it returns |
| --- | --- |
| `list_topics` | Practice files with their tags and headings |
| `search_practices(query, tag?)` | Keyword hits: file, heading, and section body |
| `get_practice(topic)` | The full practice file |
| `list_sources` | Source notes (id, title, link) |
| `get_source(id)` | The full source note |
| `get_checklist(tags[])` | Bullet rules for the given tags, ready to paste into a plan |
| `kb_version` | Git SHA of the checkout and the date of the newest source entry |

Tags for `search_practices` and `get_checklist`: `frontend`, `backend`, `db`, `infra`, `observability`, `testing`. An empty `tags` list on `get_checklist` returns every rule.

Practice files are also MCP resources at `kb://practices/<name>` (for example `kb://practices/performance`). The `apply-kb` prompt tells an agent to pull the relevant checklist before planning and to cite the rules in its PR. `/healthz` returns `{"status": "ok"}` and stays unauthenticated. The git SHA lives only on the auth-gated `kb_version` tool.

## Point a coding agent at the hosted server

Replace `http://jdad.local:8765/mcp` if the LXC ends up on a different name. If `JDAD_TOKEN` is set on the server, the client must send it.

### Claude Code plugin (preferred)

```
/plugin marketplace add JongoDB/jdad
/plugin install jdad@jdad
```

The plugin's `.mcp.json` already points at `http://jdad.local:8765/mcp` and sends `Authorization: Bearer ${JDAD_TOKEN}`. Claude Code expands `${JDAD_TOKEN}` from the environment when it starts the plugin (official plugin MCP config: `url` and `headers` support `${VAR}` and `${VAR:-default}`). Export `JDAD_TOKEN` in the environment of the Claude Code process. If the variable is unset, Claude Code warns and may send the unexpanded `${JDAD_TOKEN}` text, which the server will reject with 401. It also ships the `/jdad` slash command (`plan`, `review`, `perf`, `add <url>`) and a `jdad-performance` skill.

This repo is private, so the host that adds the marketplace needs git auth for `github.com/JongoDB/jdad`.

### Codex

In `~/.codex/config.toml`:

```toml
[mcp_servers.jdad]
url = "http://jdad.local:8765/mcp"
bearer_token_env_var = "JDAD_TOKEN"
```

### Cursor

In `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (user):

```json
{
  "mcpServers": {
    "jdad": {
      "url": "http://jdad.local:8765/mcp",
      "headers": {
        "Authorization": "Bearer ${JDAD_TOKEN}"
      }
    }
  }
}
```

Stdio still works if you would rather run the server locally, including `uvx --from git+https://github.com/JongoDB/jdad jdad-mcp` (or `git+ssh://git@github.com/JongoDB/jdad`) with `gh auth` or an SSH key on the host.

## Deploy on the LXC

`deploy/install.sh` is idempotent and is the supported first-time (and repair) path. Run it as root. It will:

- create the system user `jdad` if it does not exist (home `/opt/jdad`, nologin)
- clone the repo into `/opt/jdad` as that user (`sudo -u jdad git clone`), and `chown` the checkout to `jdad` if it already exists
- run `uv sync --frozen --no-dev` as `jdad` with `UV_PYTHON_PREFERENCE=only-system`, so the venv is `/opt/jdad/.venv` (not under `/root` or `/home`)
- install `/etc/jdad.env` at mode `0600` with the `JDAD_TOKEN=` placeholder only, and leave an existing env file alone
- install and `enable` the systemd unit. It starts the service only when `JDAD_TOKEN` is already set; otherwise it prints the command to start after you fill in the token

The `jdad` user needs git access to this private repo (a deploy key under `/opt/jdad/.ssh`, or equivalent). Install `uv` in a location the root path can see, typically `/usr/local/bin/uv`. `update.sh` / `install.sh` also look at `command -v uv`, then `/usr/local/bin/uv` and `~jdad/.local/bin/uv`, or an explicit `UV=/absolute/path/to/uv`.

The unit binds to `0.0.0.0:8765` as user `jdad`, with `UV_PYTHON_PREFERENCE=only-system`, `NoNewPrivileges`, `ProtectSystem=strict`, `ReadOnlyPaths=/opt/jdad`, `PrivateTmp`, and `ProtectHome=true`. Set `JDAD_TOKEN` in `/etc/jdad.env` before starting; without it the process will refuse that bind.

```bash
# from a checkout of this repo, or after copying deploy/ onto the host
sudo ./deploy/install.sh
# or: sudo JDAD_REPO=git@github.com:JongoDB/jdad.git ./deploy/install.sh
sudo chmod 0600 /etc/jdad.env
sudo editor /etc/jdad.env   # set JDAD_TOKEN; do not commit this file
sudo systemctl start jdad.service
curl -fsS http://127.0.0.1:8765/healthz
```

`deploy/update.sh` is idempotent: it resolves `uv` as above, runs `git` as the `jdad` user (`git pull --ff-only`), syncs deps as `jdad`, restarts only when HEAD changes, and starts the service if it is down. Run it as root (or a user that can `systemctl` this unit and `sudo -u jdad`):

```bash
sudo ./deploy/update.sh
```

## Development

```bash
uv sync
./verify
```

`./verify` runs ruff, pytest, `uv build`, and `claude plugin validate` when the Claude CLI is on `PATH` (it skips that last step with a note when it isn't). GitHub Actions is set up to run the same script on pull requests and on pushes to `main`, with `permissions: contents: read` and actions pinned to SHAs. That check is currently billing-blocked on this repo (red check; the job never starts), so local `./verify` is the proof until billing is fixed.
