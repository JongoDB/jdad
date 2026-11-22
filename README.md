# JDAD (Jon-does-agentic-dev)

Best practices pulled from videos and articles Jon sends, plus an MCP server and a Claude Code plugin that coding agents can use while they plan and build.

The MCP server is read-only. It never writes to the knowledge base and makes no network calls.

The hosted URL used in the plugin and in the agent configs below is a placeholder until a real hostname is set:

```
https://jdad.example/mcp
```

The server itself listens on `127.0.0.1:8765`. Remote clients reach it through a Cloudflare Tunnel and a Cloudflare Access service token, plus `Authorization: Bearer`. `/healthz` is the liveness probe on the same origin (the Access policy should still allow whatever you use to probe it).

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
```

`KB_ROOT` overrides the content directory. It must point at a directory that contains `practices/` and `sources/`. If unset, the server uses a checkout of this repo when it can find one, otherwise the files bundled in the package.

`JDAD_TOKEN` is optional on loopback. When set, every HTTP path except `/healthz` requires `Authorization: Bearer <token>`. Stdio does not use the token. Store the value in `/etc/jdad.env` (mode 0600) on the host; never commit it. `JDAD_ALLOWED_HOSTS` is a comma-separated list of public hostnames the MCP transport will accept in the `Host` header (loopback is always allowed; DNS-rebinding protection stays on). Set it to the tunnel hostname in the same env file.

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

Replace `https://jdad.example/mcp` with the real hostname once it exists. Clients send `Authorization: Bearer` (`JDAD_TOKEN`) and the Cloudflare Access service-token headers `CF-Access-Client-Id` / `CF-Access-Client-Secret`.

### Claude Code plugin (preferred)

```
/plugin marketplace add JongoDB/jdad
/plugin install jdad@jdad
```

The plugin's `.mcp.json` already points at the placeholder `https://jdad.example/mcp` and sends:

```
Authorization: Bearer ${JDAD_TOKEN}
CF-Access-Client-Id: ${JDAD_CF_CLIENT_ID}
CF-Access-Client-Secret: ${JDAD_CF_CLIENT_SECRET}
```

Claude Code expands `${VAR}` from the environment when it starts the plugin (official plugin MCP config: `url` and `headers` support `${VAR}` and `${VAR:-default}`). Export `JDAD_TOKEN`, `JDAD_CF_CLIENT_ID`, and `JDAD_CF_CLIENT_SECRET` in the environment of the Claude Code process. If a variable is unset, Claude Code warns and may send the unexpanded `${VAR}` text, which the server or Access will reject. It also ships the `/jdad` slash command (`plan`, `review`, `perf`, `add <url>`) and a `jdad-performance` skill.

This repo is private, so the host that adds the marketplace needs git auth for `github.com/JongoDB/jdad`.

### Codex

In `~/.codex/config.toml`:

```toml
[mcp_servers.jdad]
url = "https://jdad.example/mcp"
bearer_token_env_var = "JDAD_TOKEN"

[mcp_servers.jdad.env_http_headers]
"CF-Access-Client-Id" = "JDAD_CF_CLIENT_ID"
"CF-Access-Client-Secret" = "JDAD_CF_CLIENT_SECRET"
```

### Cursor

In `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (user):

```json
{
  "mcpServers": {
    "jdad": {
      "url": "https://jdad.example/mcp",
      "headers": {
        "Authorization": "Bearer ${JDAD_TOKEN}",
        "CF-Access-Client-Id": "${JDAD_CF_CLIENT_ID}",
        "CF-Access-Client-Secret": "${JDAD_CF_CLIENT_SECRET}"
      }
    }
  }
}
```

On a LAN or loopback setup (no Cloudflare Access), drop the `CF-Access-*` headers. If those env vars are unset, Claude Code may send the literal `${JDAD_CF_CLIENT_ID}` / `${JDAD_CF_CLIENT_SECRET}` text, which the server ignores but is confusing. A LAN `.mcp.json` looks like this:

```json
{
  "mcpServers": {
    "jdad": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp",
      "headers": {
        "Authorization": "Bearer ${JDAD_TOKEN}"
      }
    }
  }
}
```

Stdio still works if you would rather run the server locally, including `uvx --from git+https://github.com/JongoDB/jdad jdad-mcp` (or `git+ssh://git@github.com/JongoDB/jdad`) with `gh auth` or an SSH key on the host.

## Deploy on the LXC

`deploy/install.sh` is idempotent and is the supported first-time (and repair) path. Run it as root from the repo root (`sudo ./deploy/install.sh`) or by absolute path. It will:

- create the system user `jdad` if it does not exist (home `/var/lib/jdad`, nologin), or move an existing `jdad` home there
- create `/var/lib/jdad/.ssh` at mode `0700` and install `deploy/ssh-config.example` as `/var/lib/jdad/.ssh/config` (mode `0600`) if that file is missing
- clone the repo into `/opt/jdad` as that user (`sudo -u jdad git clone`), and `chown` the checkout to `jdad` if it already exists. The home directory is outside the checkout, so a deploy key in `/var/lib/jdad/.ssh` does not make `/opt/jdad` non-empty, and the uv cache lands in `/var/lib/jdad/.cache` rather than in the KB tree
- run `uv sync --frozen --no-dev` as `jdad` with `HOME=/var/lib/jdad` and `UV_PYTHON_PREFERENCE=only-system`, so the venv is `/opt/jdad/.venv` (not under `/root` or `/home`)
- install `/etc/jdad.env` at mode `0600` with the `JDAD_TOKEN=` placeholder only, and leave an existing env file alone
- install and `enable` the systemd unit. It starts the service only when `JDAD_TOKEN` is a non-empty value (not `JDAD_TOKEN=` or `JDAD_TOKEN=""`); otherwise it prints the command to start after you fill in the token

The `jdad` user needs git access to this private repo. `sudo -u jdad` has no SSH agent, so use a deploy key and an ssh config entry, not a forwarded agent. The key and `known_hosts` have to exist before the first successful clone, but `install -o jdad` needs the user first. Use this bootstrap order:

1. Create the `jdad` user and home (this does not clone or start the service):

   ```bash
   sudo ./deploy/install.sh --bootstrap-user
   ```

   That creates `/var/lib/jdad` and `/var/lib/jdad/.ssh` (mode `0700`) and installs `deploy/ssh-config.example` as `/var/lib/jdad/.ssh/config` (mode `0600`) if it is missing. You can create the user and directories by hand instead; the flags above are the supported path.

2. Place the deploy key:

   ```bash
   sudo install -o jdad -g jdad -m 0600 /path/to/jdad_deploy_key /var/lib/jdad/.ssh/id_ed25519
   ```

   The example ssh config is:

   ```
   Host github.com
     HostName github.com
     User git
     IdentityFile /var/lib/jdad/.ssh/id_ed25519
     IdentitiesOnly yes
   ```

3. Pin `github.com` in `/var/lib/jdad/.ssh/known_hosts` using GitHub's [published SSH host keys](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints). Check the fingerprints against that page. Do not run `ssh-keyscan github.com`, and do not set `StrictHostKeyChecking accept-new`.

   Write these published host keys (from that page; re-check the page if they look different) to a file, for example `/tmp/github_known_hosts`:

```
github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl
github.com ecdsa-sha2-nistp256 AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBEmKSENjQEezOmxkZMy7opKgwFB9nkt5YRrYMjNuG5N87uRgg6CLrbo5wAdT/y6v0mKV0U2w0WZ2YB/++Tpockg=
github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1aNUkY4Ue1gvwnGLVlOhGeYrnZaMgRK6+PKCUXaDbC7qtbW8gIkhL7aGCsOr/C56SJMy/BCZfxd1nWzAOxSDPgVsmerOBYfNqltV9/hWCqBywINIR+5dIg6JTJ72pcEpEjcYgXkE2YEFXV1JHnsKgbLWNlhScqb2UmyRkQyytRLtL+38TGxkxCflmO+5Z8CSSNY7GidjMIZ7Q4zMjA2n1nGrlTDkzwDCsw+wqFPGQA179cnfGWOWRVruj16z6XyvxvjJwbz0wQZ75XK5tKSb7FNyeIEs4TT4jk+S4dhPeAUC5y+bDYirYgM4GC7uEnztnZyaVWQ7B381AK4Qdrwt51ZqExKbQpTUNn+EjqoTwvqNj4kqx5QUCI0ThS/YkOxJCXmPUWZbhjpCg56i+2aB6CmK2JGhn57K5mj0MNdBXA4/WnwH6XoPWJzK5Nyu2zB3nAZp+S5hpQs+p1vN1/wsjk=
```

   Then check the fingerprints and install the file only if they match:

```bash
ssh-keygen -lf /tmp/github_known_hosts -E sha256
# Expect, matching GitHub's published fingerprints page:
#   SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU (ED25519)
#   SHA256:p2QAMXNIC1TJYWeIOttrVc98/R1BUFWu3/LiyKgUfQM (ECDSA)
#   SHA256:uNiVztksCsDhcc0u9e8BujQXVUpKZIDTMczCvj3tD2s (RSA)
sudo install -o jdad -g jdad -m 0644 /tmp/github_known_hosts /var/lib/jdad/.ssh/known_hosts
```

   If GitHub rotates a host key, take the new key from that same published page, check the new fingerprint, and replace the line. Do not accept a key just because `ssh-keyscan` printed it.

4. Run the full install (from the repo root, or by absolute path):

   ```bash
   sudo ./deploy/install.sh
   # or: sudo /opt/jdad/deploy/install.sh
   # or: sudo JDAD_REPO=git@github.com:JongoDB/jdad.git ./deploy/install.sh
   sudo chmod 0600 /etc/jdad.env
   sudo editor /etc/jdad.env   # set a non-empty JDAD_TOKEN and JDAD_ALLOWED_HOSTS; do not commit this file
   sudo systemctl start jdad.service
   curl -fsS http://127.0.0.1:8765/healthz
   ```

Install `uv` in a location the root path can see, typically `/usr/local/bin/uv`, before step 4. `update.sh` / `install.sh` also look at `command -v uv`, then `/usr/local/bin/uv` and `~jdad/.local/bin/uv` (`/var/lib/jdad/.local/bin/uv`), or an explicit `UV=/absolute/path/to/uv`.

The unit binds to `127.0.0.1:8765` as user `jdad`, with `UV_PYTHON_PREFERENCE=only-system`, `NoNewPrivileges`, `ProtectSystem=strict`, `ReadOnlyPaths=/opt/jdad`, `PrivateTmp`, and `ProtectHome=true`. Set a non-empty `JDAD_TOKEN` in `/etc/jdad.env` before starting, and set `JDAD_ALLOWED_HOSTS` to the public hostname if you will reach the server through a tunnel that forwards that `Host` header. Expose the server with a Cloudflare Tunnel (below), not by binding to `0.0.0.0`.

`deploy/update.sh` is idempotent: it resolves `uv` as above, runs `git` as the `jdad` user (`git pull --ff-only`), syncs deps as `jdad`, restarts only when HEAD changes, and starts the service if it is down. Run it as root from the repo root (or a user that can `systemctl` this unit and `sudo -u jdad`):

```bash
sudo ./deploy/update.sh
```

## Remote access via Cloudflare Tunnel

Keep the server on its default bind, `127.0.0.1:8765`. Do not publish that port on the LXC.

Run `cloudflared` inside the LXC with the service URL `http://127.0.0.1:8765` (`127.0.0.1` rather than `localhost`, because the unit is IPv4-only and `localhost` can resolve to `::1`). Put a Cloudflare Access application on the tunnel hostname, with a Service Auth policy that accepts an Access service token.

`cloudflared` forwards the public `Host` header by default. The MCP SDK's DNS-rebinding protection only allows loopback hosts unless you say otherwise, so a request with `Host: jdad.example` would get `421 Invalid Host header`. Pick one of:

- Set `JDAD_ALLOWED_HOSTS` in `/etc/jdad.env` to the public hostname (comma-separated if you have more than one), then restart the unit. Loopback stays allowed; the protection is not disabled. Example: `JDAD_ALLOWED_HOSTS=jdad.example`.
- Or configure cloudflared `originRequest.httpHostHeader` to an allowed loopback host, for example `127.0.0.1:8765`, so the backend sees a loopback `Host` instead of the public name.

Clients send all three of:

- `Authorization: Bearer <JDAD_TOKEN>`
- `CF-Access-Client-Id: <JDAD_CF_CLIENT_ID>`
- `CF-Access-Client-Secret: <JDAD_CF_CLIENT_SECRET>`

The plugin `.mcp.json` and the Codex / Cursor examples already use those header names and the placeholder URL `https://jdad.example/mcp`. Leave that URL as a placeholder until the real hostname is chosen, then replace it in `.mcp.json` and in the agent configs, and put that hostname in `JDAD_ALLOWED_HOSTS` (unless you use `httpHostHeader`).

## Development

```bash
uv sync
./verify
```

`./verify` runs `bash -n` on each deploy script, a sandboxed invocation/token-parsing check (it drops privileges if run as root, and will not run a real `install.sh` against the host), ruff, pytest, `uv build`, and `claude plugin validate` when the Claude CLI is on `PATH` (it skips that last step with a note when it isn't). GitHub Actions is set up to run the same script on pull requests and on pushes to `main`, with `permissions: contents: read` and actions pinned to SHAs. That check is currently billing-blocked on this repo (red check; the job never starts), so local `./verify` is the proof until billing is fixed.
