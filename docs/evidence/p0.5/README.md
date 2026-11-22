# P0.5 evidence: hosted endpoint deployed and proven (2026-11-22)

These are raw outputs for roadmap item P0.5 and [ADR 0005](../../adr/0005-hosted-deploy-cloudflare-full-strict.md). They were captured after the deploy of `main` c90178b (v0.1.6) at 2:35 PM ET.

**Redaction.** The bearer token was read from `~/.config/jdad/jdad.env` inside each remote command and never printed. Every occurrence of the token, every `Bearer <value>` and every `mcp-session-id` value was replaced with `[REDACTED]`. `docker inspect` is limited to named fields, because `Config.Env` holds the token.

| File | What | Where it ran |
| --- | --- | --- |
| [public-from-box.txt](public-from-box.txt) | `curl -sS -i` of `/healthz` (200) and `/mcp` with no token (401), with `server: cloudflare` and `cf-ray` | Daisy's box, over the public internet, 2:43 PM ET |
| [droplet.txt](droplet.txt) | See the list below | On the droplet (`ssh droplet` via Jon's Mac), 2:44:36–2:44:38 PM ET |
| `cloudflare-config-rule.png` | Cloudflare dashboard, Rules > Configuration Rules: rule "hostname matches jdad-mcp.jondevs.com", match Hostname (wildcard) `jdad-mcp.jondevs.com`, action SSL, status Active | Jon's screenshot, sent in Daisy's Grok Bot chat 2026-11-22 2:43 PM ET (not committed; image files not exportable from chat) |
| `cloudflare-ssl-strict.png` | The same rule's SSL setting: encryption mode **Strict**, placed First | Jon's screenshot, sent in Daisy's Grok Bot chat 2026-11-22 2:43 PM ET (not committed; image files not exportable from chat) |

`droplet.txt` contains:
- `docker ps -a`: `jdad-jdad-1` healthy on `jdad:c90178b…`, 443->8443; NetBird containers Exited (0)
- `docker inspect` hardening fields:
  - `ReadonlyRootfs=true`
  - `CapDrop=[ALL]`
  - `no-new-privileges:true`
  - `User=1000:1000`
  - tls mounted read-only
- `docker exec`: uid 1000, `JDAD_GIT_SHA` c90178b, and a write to `/` that fails
- `ss` and `curl` on port 80: nothing is listening (curl exit 7)
- Origin cert details, plus matching SHA-256 hashes of the cert and key public keys
- `curl --cacert` against the Cloudflare Origin CA RSA root: `ssl_verify_result=0`, 200
- 421 for `Host: evil.example.com` at the origin
- Public calls through Cloudflare:
  - wrong token: 401
  - valid token, `initialize`: 200
  - valid token, `notifications/initialized`: 202
  - valid token, `tools/list`: 200, 7 tools
  - valid token, `tools/call kb_version`: 200, sha c90178b, `dirty: false`

## How each P0.5 criterion is met

| Criterion | Evidence |
| --- | --- |
| Container `JDAD_GIT_SHA` = `main` head | droplet.txt: `docker exec` output and `kb_version` both show c90178b |
| `initialize`, `tools/list`, `tools/call` return 200 with a valid token | droplet.txt, public URL, `server: cloudflare` |
| 401 with no token | public-from-box.txt (also 401 with a wrong token in droplet.txt) |
| 421 for a non-allowlisted Host at the origin | droplet.txt |
| `curl --cacert` with the Origin CA root verifies | droplet.txt: `ssl_verify_result=0` |
| Cloudflare SSL mode for the host is Full (strict) | the two screenshots above |
| Tokens redacted | this whole directory |
