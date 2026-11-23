# JDAD (Jon-does-agentic-dev)

Best practices pulled from videos and articles Jon sends, plus an MCP server and a Claude Code plugin that coding agents can use while they plan and build.

The MCP server is read-only. It never writes to the knowledge base and makes no network calls.

The hosted URL used in the plugin and in the agent configs below is:

```
https://jdad-mcp.jondevs.com/mcp
```

JDAD runs as the only Docker container on a DigitalOcean droplet. Cloudflare's orange-cloud proxy terminates TLS for `https://jdad-mcp.jondevs.com` and connects to the origin with Full (strict) TLS. There is no tunnel, no Access, and no plaintext hop to the origin. Clients send `Authorization: Bearer`. `/healthz` is the liveness probe on the same origin. Plain HTTP is not supported for the public deploy.

## Layout

```
practices/                 deduped rules, one topic per file, tagged by area
sources/                   one file per source: link, author, date, and a verbatim record
src/jdad/                  stdio + streamable HTTP MCP server (official `mcp` Python SDK)
deploy/                    Docker Compose, update-docker.sh, and a leftover systemd unit
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
4. Bump the patch (or minor) version in lockstep (`pyproject.toml`, `src/jdad/__init__.py`, `uv.lock`, `.claude-plugin/plugin.json`, and the marketplace plugin entry). `./verify` fails if they differ.
5. Do not put secrets, tokens, or credentials in this repo.

Agents working in this repo follow [AGENTS.md](AGENTS.md), where every rule has an ID; [CLAUDE.md](CLAUDE.md) imports it and adds Claude Code notes.

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

`JDAD_TOKEN` is optional on loopback. When set, every HTTP path except `/healthz` requires `Authorization: Bearer <token>`. Stdio does not use the token. The Docker deploy binds `0.0.0.0`, so a non-empty token is required (the image does not pass `--allow-no-auth`). `JDAD_TOKEN_FILE` names a file holding only the token (it must not be readable by group or others); the server reads it once at startup and refuses to start if both `JDAD_TOKEN` and `JDAD_TOKEN_FILE` are set. The Docker deploy uses the file, `~/.config/jdad/token` (mode 0400) on the droplet, mounted as a compose secret, so the value never appears in the container environment or `docker inspect`. Never commit it. `JDAD_ALLOWED_HOSTS` is a comma-separated list of public hostnames the MCP transport will accept in the `Host` header (loopback is always allowed; DNS-rebinding protection stays on). For this host it is `jdad-mcp.jondevs.com`, which also allows Origin `https://jdad-mcp.jondevs.com` because Cloudflare forwards the original Host header.

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

The default URL is `https://jdad-mcp.jondevs.com/mcp`. Clients send only `Authorization: Bearer` (`JDAD_TOKEN`). Do not put Cloudflare Access headers in the default config: if those env vars are unset, clients send the literal `${JDAD_CF_CLIENT_ID}` / `${JDAD_CF_CLIENT_SECRET}` text.

### Claude Code plugin (preferred)

```
/plugin marketplace add JongoDB/jdad
/plugin install jdad@jdad
```

The plugin's `.mcp.json` already points at `https://jdad-mcp.jondevs.com/mcp` and sends:

```
Authorization: Bearer ${JDAD_TOKEN}
```

Claude Code expands `${JDAD_TOKEN}` from the environment when it starts the plugin (official plugin MCP config: `url` and `headers` support `${VAR}` and `${VAR:-default}`). Export `JDAD_TOKEN` in the environment of the Claude Code process. If the variable is unset, Claude Code warns and may send the unexpanded `${JDAD_TOKEN}` text, which the server rejects with 401. It also ships the `/jdad` slash command (`plan`, `review`, `perf`, `add <url>`) and a `jdad-performance` skill.

This repo is private, so the host that adds the marketplace needs git auth for `github.com/JongoDB/jdad`.

### Codex

In `~/.codex/config.toml`:

```toml
[mcp_servers.jdad]
url = "https://jdad-mcp.jondevs.com/mcp"
bearer_token_env_var = "JDAD_TOKEN"
```

### Cursor

In `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (user):

```json
{
  "mcpServers": {
    "jdad": {
      "url": "https://jdad-mcp.jondevs.com/mcp",
      "headers": {
        "Authorization": "Bearer ${JDAD_TOKEN}"
      }
    }
  }
}
```

If you later put a Cloudflare Access Service Auth policy in front of the hostname, add these headers as an optional variant (and export the env vars). Leave them out unless Access is actually enabled:

```
CF-Access-Client-Id: ${JDAD_CF_CLIENT_ID}
CF-Access-Client-Secret: ${JDAD_CF_CLIENT_SECRET}
```

In Codex that is `env_http_headers` mapping those header names to `JDAD_CF_CLIENT_ID` and `JDAD_CF_CLIENT_SECRET`.

A local `.mcp.json` (stdio is also fine) looks like this:

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

That example is loopback only. To reach the server from another machine on your LAN (for example `https://jdad.lan:8765/mcp`), the server must:

- bind a non-loopback address (`--host 0.0.0.0` or the LAN IP), which requires `JDAD_TOKEN`;
- serve TLS (`--ssl-certfile` / `--ssl-keyfile`, with a cert the client trusts for that name), because plain HTTP sends the token unencrypted and non-loopback hosts only get `https://` origins (browser-style clients that send `Origin: http://…` are rejected with 403; header-less MCP clients aren't affected);
- list the name the client puts in `Host` in `JDAD_ALLOWED_HOSTS` (for example `JDAD_ALLOWED_HOSTS=jdad.lan`), or requests get `421 Invalid Host header`.

If you can't do all three, use stdio instead.

Stdio still works if you would rather run the server locally, including `uvx --from git+https://github.com/JongoDB/jdad jdad-mcp` (or `git+ssh://git@github.com/JongoDB/jdad`) with `gh auth` or an SSH key on the host.

## Deploy on a droplet with Docker behind Cloudflare proxy

This is the supported deploy. JDAD is the only container on the droplet. Cloudflare's orange-cloud proxy terminates TLS for `https://jdad-mcp.jondevs.com` and forwards to the origin on port 443 with **Full (strict)** TLS. There is no tunnel and no Access. Plain HTTP (including Cloudflare Flexible SSL) is not supported for this public deploy: the Cloudflare-to-origin hop must be TLS, using a [Cloudflare Origin CA certificate](https://developers.cloudflare.com/ssl/origin-configuration/origin-ca/) whose private key never leaves the droplet.

SSL/TLS mode in Cloudflare is zone-wide. Set a **Configuration Rule** that applies **Full (strict)** only to `jdad-mcp.jondevs.com` (Rules → Configuration Rules → hostname equals `jdad-mcp.jondevs.com` → SSL → Full (strict)), so other hostnames in the zone are not forced onto this mode.

Authenticated Origin Pulls are an optional extra: they make Cloudflare present a client certificate so the origin can reject traffic that did not come through Cloudflare. This compose file does not yet verify origin-pull client certs; if you add them later, terminate or verify that client cert in front of `jdad-mcp` and still keep Full (strict).

### Origin certificate (private key stays on the droplet)

1. On the droplet, as the deploy user:

   ```bash
   mkdir -p ~/.config/jdad/tls
   chmod 700 ~/.config/jdad ~/.config/jdad/tls
   openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
     -keyout ~/.config/jdad/tls/origin.key \
     -out ~/.config/jdad/tls/origin.csr \
     -subj "/CN=jdad-mcp.jondevs.com"
   chmod 600 ~/.config/jdad/tls/origin.key
   ```

   The private key must be readable only by the uid the container runs as (the deploy user: `update-docker.sh` and compose set `user:` to `$(id -u):$(id -g)`). Mode `0600` or `0400`, owned by that user. Never copy the key off the droplet. The CSR is not secret.

2. In the Cloudflare dashboard: SSL/TLS → Origin Server → Create Certificate → **Use my private key and CSR**. Paste only the CSR. Save the returned certificate as `~/.config/jdad/tls/origin.crt` (mode `0644` is fine).

### Firewall

Create a DigitalOcean cloud firewall attached to the droplet:

- Inbound TCP 443 only from [Cloudflare IP ranges](https://www.cloudflare.com/ips/). Use both IPv4 and IPv6 lists.
- Inbound SSH only from your own IPs.
- Do not publish port 80.
- Leave outbound open, or at least allow the origin to reach Cloudflare and GitHub.

Do this in the DigitalOcean control panel (or `doctl compute firewall`); a host-local `ufw` rule is not a substitute for the cloud firewall. Docker-published ports bypass ufw.

### Read-only deploy key

The checkout on the droplet pulls this private repo as the deploy user (no passwordless sudo, no SSH agent required):

1. On the droplet, as the deploy user:

   ```bash
   mkdir -p ~/.ssh
   chmod 700 ~/.ssh
   ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_jdad -N "" -C "jdad-droplet-deploy"
   ```

2. Add the public key as a **read-only** deploy key on `JongoDB/jdad` (GitHub: repo Settings → Deploy keys, leave "Allow write access" unchecked).

3. Pin `github.com` in `~/.ssh/known_hosts` from GitHub's [published SSH host keys](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints). Check the fingerprints against that page. Do not run `ssh-keyscan github.com`, and do not set `StrictHostKeyChecking accept-new`. See the known_hosts block under the leftover systemd install notes below for the published keys and expected SHA256 fingerprints.

4. Install an ssh config entry so `git` uses that key without an agent:

   ```
   Host github.com
     HostName github.com
     User git
     IdentityFile ~/.ssh/id_ed25519_jdad
     IdentitiesOnly yes
   ```

   Mode `0600` on the key, the config, and (after pinning) `known_hosts`.

### Token and first install

Generate the bearer token straight into its own file; never echo it. The token file is mounted into the container as a compose secret and read once at startup, so it isn't visible through `docker inspect` the way an environment variable is.

To rotate: write a new token over the file the same way (`chmod 600` it first if it is 0400, then back to 0400), restart the container with `docker compose -p jdad -f deploy/docker-compose.yml restart jdad` (no rebuild needed) or `./deploy/update-docker.sh`, then update every client. The previous token stops working at the restart.

**Upgrading an older deploy** that keeps `JDAD_TOKEN` in `~/.config/jdad/jdad.env`: run `./deploy/migrate-token.sh` once (it moves the value into `~/.config/jdad/token` at mode 0400 without printing it, checks the copy, and deletes the line from the env file), then `./deploy/update-docker.sh`. `update-docker.sh` refuses to run while the env file still sets `JDAD_TOKEN`.

**Rolling back across the migration.** Images built before the token file read only `JDAD_TOKEN`. Every image from this release on carries the label `io.jdad.token-file=1`. When `update-docker.sh` rolls back to an image without it (for example, the first update after migrating fails its health check), it adds `deploy/compose.legacy-token.yml` and passes the token from `~/.config/jdad/token` as `JDAD_TOKEN` for that container only. The log says "predates the token file". The value is read inside the script, never on a command line, but it is in that container's environment (`docker inspect`), as it was before the migration. The next successful deploy recreates the container without it. `tests/test_docker.sh` covers this with a stand-in image; `JDAD_TEST_LEGACY_REF=<ref>` runs the same test against the real image built from that commit.

To undo the migration by hand instead (stay on an old commit for good): check out the old commit; put `JDAD_TOKEN=` plus the value from the token file back into `jdad.env` without echoing it (for example `{ printf 'JDAD_TOKEN='; cat ~/.config/jdad/token; } >> ~/.config/jdad/jdad.env`); then run the old commit's `update-docker.sh`. Delete the token file only once that deploy is healthy.

Use a dedicated **non-root** deploy user in the `docker` group (on a fresh DigitalOcean droplet you log in as root; create the user first, for example `adduser deploy && usermod -aG docker deploy`). The container runs as the deploy user's uid, and `update-docker.sh` refuses to run with `JDAD_UID=0`.

```bash
# as the non-root deploy user, who can talk to the docker daemon
git clone git@github.com:JongoDB/jdad.git
cd jdad

umask 077
mkdir -p ~/.config/jdad
openssl rand -hex 32 > ~/.config/jdad/token
chmod 400 ~/.config/jdad/token
printf 'JDAD_ALLOWED_HOSTS=jdad-mcp.jondevs.com\n' > ~/.config/jdad/jdad.env
chmod 600 ~/.config/jdad/jdad.env
# do not commit either file

# Origin cert and key must already be in ~/.config/jdad/tls/ as above
export JDAD_GIT_SHA="$(git rev-parse HEAD)"
export JDAD_UID="$(id -u)"
export JDAD_GID="$(id -g)"
docker compose -f deploy/docker-compose.yml up -d --build
# Local probe: connect to 127.0.0.1, verify the origin certificate for the
# public name, trusting only that certificate (no -k).
curl -fsS --cacert ~/.config/jdad/tls/origin.crt \
  --resolve jdad-mcp.jondevs.com:443:127.0.0.1 https://jdad-mcp.jondevs.com/healthz
```

> **Warning:** `docker compose -f deploy/docker-compose.yml config` prints the fully expanded config, including everything in the env file (and `JDAD_TOKEN`, on a deploy that hasn't been migrated to the token file). Don't paste its output into chats, tickets, PRs or logs. To check the file without values, use `docker compose -f deploy/docker-compose.yml config --quiet` (exit code only).

`deploy/docker-compose.yml` uses the project name `jdad` (so this first install and `update-docker.sh` are the same compose project), builds from the repo with `JDAD_GIT_SHA` baked into the image, publishes `443:8443`, restarts unless stopped, reads `~/.config/jdad/jdad.env`, mounts `~/.config/jdad/token` as the secret `/run/secrets/jdad_token` (`JDAD_TOKEN_FILE`), mounts `~/.config/jdad/tls/` read-only, sets `JDAD_ALLOWED_HOSTS=jdad-mcp.jondevs.com` (Origin `https://jdad-mcp.jondevs.com` is also allowed), and runs with a read-only root filesystem, `tmpfs` on `/tmp`, `cap_drop: [ALL]`, and `no-new-privileges`. The container process runs as the deploy user's uid so it can read a `0600` key and the `0400` token file. It binds `0.0.0.0:8443` with TLS, so it will refuse to start without a token. `--allow-no-auth` is not used.

`jdad-mcp` also accepts `--ssl-certfile` / `--ssl-keyfile`, or `JDAD_SSL_CERTFILE` / `JDAD_SSL_KEYFILE`.

Later updates (idempotent; fails loudly; rolls back to the previous image if healthz fails):

```bash
./deploy/update-docker.sh
```

Before touching the running container it checks that `JDAD_UID` isn't 0; that the token file exists, isn't a symlink, is owned by the deploy uid, has no group or other permission bits and isn't empty; that the env file exists and no longer sets `JDAD_TOKEN`; that the certificate is a readable, unexpired PEM whose public key matches the private key (`openssl x509 -pubkey` vs `openssl pkey -pubout`); and that the key has no group or other permission bits. Then it sets `JDAD_GIT_SHA` from `git rev-parse HEAD`, does `git pull --ff-only`, `docker compose up -d --build`, and probes `/healthz` on the published port (443 in production) with `curl --cacert <origin.crt> --resolve jdad-mcp.jondevs.com:<port>:127.0.0.1`: the origin certificate must verify for the public name (no `-k`), and the body must be `{"status":"ok"}`. A wrong, expired or mismatched certificate fails the update and triggers the rollback. A rollback to an image from before the token file gets `JDAD_TOKEN` from the token file (see "Rolling back across the migration"). `JDAD_HEALTH_HOST` overrides the name. After a healthy update it prunes old `jdad:<sha>` images, keeping the current one and the previous one (also tagged `jdad:previous`) for rollback.

`JDAD_ALLOWED_HOSTS` entries are lowercased, and wildcard entries such as `*` or `*.jondevs.com` are rejected at startup. Public hosts get `https://` origins only; `http://` origins are allowed for loopback.

## Alternative: systemd on a host

This is not how the DigitalOcean droplet is run. `deploy/install.sh` remains for a host-installed layout.

`deploy/install.sh` is idempotent and is the first-time (and repair) path for this layout. Run it as root from the repo root (`sudo ./deploy/install.sh`) or by absolute path. It will:

- create the system user `jdad` if it does not exist (home `/var/lib/jdad`, nologin), or move an existing `jdad` home there
- create `/var/lib/jdad/.ssh` at mode `0700` and install `deploy/ssh-config.example` as `/var/lib/jdad/.ssh/config` (mode `0600`) if that file is missing
- clone the repo into `/opt/jdad` as that user (`sudo -u jdad git clone`), and `chown` the checkout to `jdad` if it already exists. The home directory is outside the checkout, so a deploy key in `/var/lib/jdad/.ssh` does not make `/opt/jdad` non-empty, and the uv cache lands in `/var/lib/jdad/.cache` rather than in the KB tree
- run `uv sync --frozen --no-dev` as `jdad` with `HOME=/var/lib/jdad` and `UV_PYTHON_PREFERENCE=only-system`, so the venv is `/opt/jdad/.venv` (not under `/root` or `/home`)
- install `/etc/jdad.env` at mode `0600` from `deploy/jdad.env.example` (no token; add a `JDAD_TOKEN=` line yourself, or point `JDAD_TOKEN_FILE` at a 0400 file), and leave an existing env file alone
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

The unit binds to `127.0.0.1:8765` as user `jdad`, with `UV_PYTHON_PREFERENCE=only-system`, `NoNewPrivileges`, `ProtectSystem=strict`, `ReadOnlyPaths=/opt/jdad`, `PrivateTmp`, and `ProtectHome=true`. Set a non-empty `JDAD_TOKEN` in `/etc/jdad.env` before starting, and set `JDAD_ALLOWED_HOSTS` to the public hostname if a proxy forwards that `Host` header.

`deploy/update.sh` is idempotent: it resolves `uv` as above, runs `git` as the `jdad` user (`git pull --ff-only`), syncs deps as `jdad`, restarts only when HEAD changes, and starts the service if it is down. Run it as root from the repo root (or a user that can `systemctl` this unit and `sudo -u jdad`):

```bash
sudo ./deploy/update.sh
```

## Optional: remote access via Cloudflare Tunnel

This is not how `jdad-mcp.jondevs.com` is exposed (that hostname uses the orange-cloud proxy, with no tunnel and no Access).


Keep the server on its default bind, `127.0.0.1:8765`. Do not publish that port on the LXC.

Run `cloudflared` inside the LXC with the service URL `http://127.0.0.1:8765` (`127.0.0.1` rather than `localhost`, because the unit is IPv4-only and `localhost` can resolve to `::1`). Put a Cloudflare Access application on the tunnel hostname, with a Service Auth policy that accepts an Access service token.

`cloudflared` forwards the public `Host` header by default. The MCP SDK's DNS-rebinding protection only allows loopback hosts unless you say otherwise, so a request with `Host: jdad.example` would get `421 Invalid Host header`. Pick one of:

- Set `JDAD_ALLOWED_HOSTS` in `/etc/jdad.env` to the public hostname (comma-separated if you have more than one), then restart the unit. Loopback stays allowed; the protection is not disabled. Example: `JDAD_ALLOWED_HOSTS=jdad.example`.
- Or configure cloudflared `originRequest.httpHostHeader` to an allowed loopback host, for example `127.0.0.1:8765`, so the backend sees a loopback `Host` instead of the public name.

Clients send all three of:

- `Authorization: Bearer <JDAD_TOKEN>`
- `CF-Access-Client-Id: <JDAD_CF_CLIENT_ID>`
- `CF-Access-Client-Secret: <JDAD_CF_CLIENT_SECRET>`

If you use this path, add the Access headers as the optional variant in the agent configs, set `JDAD_ALLOWED_HOSTS` to the tunnel hostname (or use `httpHostHeader`), and point the client URL at that hostname.

## Development

```bash
uv sync
./verify
```

`./verify` runs `bash -n` on each deploy script, `uv lock --check`, a version-lockstep check, a sandboxed invocation/token-parsing check (it drops privileges if run as root, and will not run a real `install.sh` against the host), a Docker image and compose smoke test when Docker is available (it skips with a note when it isn't; it runs under its own compose project `jdad-test-<pid>`, image repo and an ephemeral loopback port, refuses to run if a compose project named `jdad` exists on the daemon, and tests `update-docker.sh` rollback with a deliberately broken commit), ruff, pytest, `uv build`, and `claude plugin validate` when the Claude CLI is on `PATH` (it skips that last step with a note when it isn't, except under `CI`, where a missing CLI fails the run; the workflow installs a pinned CLI). `.python-version` pins Python 3.12 for `uv`, matching the image. `./verify` runs on Linux and on macOS (OrbStack or Docker Desktop). GitHub Actions is set up to run the same script on pull requests and on pushes to `main`, with `permissions: contents: read` and actions pinned to SHAs. That check is currently billing-blocked on this repo (red check; the job never starts), so local `./verify` is the proof until billing is fixed.
