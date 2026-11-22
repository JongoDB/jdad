# 0005: Hosted deploy: Docker on the droplet behind Cloudflare Full (strict)

- Status: Accepted (2026-11-22: P0.5 passed, deployed at c90178b)
- Date: 2026-11-22
- Deciders: Jon, roadmap author

## Context

[ADR 0003](0003-stdio-plus-hosted-http-mcp.md) (Accepted) covers the server. PR #2 (merged as 2022a8a) adds the hosted deployment at `jdad-mcp.jondevs.com`, on Jon's DigitalOcean droplet, with the DNS record proxied by Cloudflare (orange cloud). Jon chose to let Cloudflare handle public TLS, to run JDAD as the only container on the droplet, and to not use a Cloudflare Tunnel. The code is on `main`, and on 2026-11-22 the deployment was proven live (roadmap P0.5, evidence in [ROADMAP.md](../../ROADMAP.md)), so this ADR is Accepted.

## Decision (as merged from PR #2, head 68d42b7, merge 2022a8a)

1. **Container.** A Docker image run by Compose project `jdad`, published `443:8443`. The container runs with a read-only root filesystem, a tmpfs `/tmp`, all capabilities dropped and `no-new-privileges`. The image bakes in `JDAD_GIT_SHA` so the running revision is visible.
2. **TLS: Cloudflare Full (strict) with an Origin CA certificate.** The origin serves TLS itself with a Cloudflare Origin CA certificate. The private key is generated on the droplet and never leaves it. The cert and key live in `${HOME}/.config/jdad/tls` and are mounted read-only at `/tls`, passed via `JDAD_SSL_CERTFILE` / `JDAD_SSL_KEYFILE` (or `--ssl-certfile` / `--ssl-keyfile`).
3. **Cloudflare scope.** Full (strict) is set with a Configuration Rule that matches only `jdad-mcp.jondevs.com`, so other hostnames in the zone keep their settings.
4. **No plaintext.** Port 80 isn't published. Plain HTTP at the origin and Cloudflare's Flexible mode aren't supported.
5. **Host allowlist.** `JDAD_ALLOWED_HOSTS=jdad-mcp.jondevs.com`, with the bearer token from ADR 0003.
6. **Plugin default.** The plugin's `.mcp.json` URL changes from the old placeholder (an `example` host) to `https://jdad-mcp.jondevs.com/mcp`, and the `CF-Access-Client-Id` / `CF-Access-Client-Secret` headers are dropped, leaving only `Authorization: Bearer ${JDAD_TOKEN}` (no Cloudflare Access in front of the endpoint).
7. **Deferred.** Authenticated Origin Pulls are optional and not implemented. Rate limiting / WAF is deferred to roadmap item P5.6.

## Consequences

- The droplet is a dependency; stdio from a checkout is the fallback when it's down.
- The origin certificate is trusted only by Cloudflare, so the origin must not be used directly by clients.
- Until Authenticated Origin Pulls (or an IP allowlist) is added, anyone who finds the droplet's IP can reach the origin; the bearer token is the only gate there.

## Alternatives considered

The first two reflect Jon's choices in chat; the third is the roadmap author's note, not from PR #2.


- **Cloudflare Tunnel**: no open inbound port, but Jon chose proxied DNS without a tunnel.
- **Flexible TLS (plain HTTP to the origin)**: rejected; the bearer token would cross the internet in plaintext between Cloudflare and the droplet.
- **Let's Encrypt at the origin**: works, but needs port 80 or DNS-01 automation; the Origin CA cert is long-lived and needs neither.
