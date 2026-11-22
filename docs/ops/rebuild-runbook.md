# Runbook: rebuild the hosted endpoint from nothing

When to use this: the droplet is lost, compromised or unrecoverable, or it is being moved. Everything on it can be regenerated; nothing on it is the only copy of anything. The KB lives in git, and the token, origin certificate and deploy key are all replaceable. Roadmap P0.9, JON-1344.

Time: about an hour, mostly waiting on DNS and Cloudflare. Every step below runs on the new host or in a dashboard. Never paste a token, key or `docker compose config` output into chat, tickets or PRs.

## What exists today (2026-11-22)

| Piece | Where | Regenerate by |
| --- | --- | --- |
| Droplet | DigitalOcean, about 2 GB RAM, 1 vCPU, Ubuntu 24.04 | Create a new one (step 1) |
| DNS | `jdad-mcp.jondevs.com`, proxied (orange cloud) in Cloudflare | Point the A/AAAA records at the new IP (step 8) |
| TLS mode | Cloudflare Configuration Rule: Full (strict) for this hostname only | Unchanged by a rebuild |
| Origin certificate | `~/.config/jdad/tls/origin.{crt,key}`, a Cloudflare Origin CA cert | New CSR on the new host (step 4); revoke the old cert in Cloudflare |
| Bearer token | `~/.config/jdad/token` (0400) | New token (step 5); clients must be updated |
| Deploy key | `~/.ssh/id_ed25519_jdad`, read-only key "droplet (read-only)" on `JongoDB/jdad` | New key (step 3); delete the old one in GitHub |
| Host firewall | `jdad-firewall.service`, `/etc/jdad/cloudflare/` (PR #7) | Step 7 |
| NetBird stack | four stopped containers on the old droplet (see below) | Not part of JDAD; rebuild separately if wanted |

## Steps

1. **Host.** Create the droplet (Ubuntu 24.04), add your SSH key, and open a second SSH session to keep for the whole run. Install Docker Engine and the compose plugin from Docker's apt repository. Create the deploy user: `adduser deploy && usermod -aG docker deploy`. Turn on unattended security upgrades.
2. **Cloud firewall** (DigitalOcean): inbound 443 only from Cloudflare's ranges, SSH only from your IPs, nothing on 80. See README "Firewall", layer 2.
3. **Deploy key**, as `deploy`: follow README "Read-only deploy key". Pin GitHub's host keys from the published fingerprints; never `ssh-keyscan`. Add the public key to `JongoDB/jdad` as read-only. Once the repo is public an HTTPS clone works without a key, and this step becomes optional.
4. **Origin certificate**, as `deploy`: README "Origin certificate". Generate the key and CSR on the host and paste only the CSR into Cloudflare. Prefer a certificate for `jdad-mcp.jondevs.com` only (README "Origin certificate exposure"). Revoke the old certificate in Cloudflare once the new host serves.
5. **Token**: `umask 077; mkdir -p ~/.config/jdad; openssl rand -hex 32 > ~/.config/jdad/token; chmod 400 ~/.config/jdad/token`, and `printf 'JDAD_ALLOWED_HOSTS=jdad-mcp.jondevs.com\n' > ~/.config/jdad/jdad.env; chmod 600 ~/.config/jdad/jdad.env`. To keep clients working, copy the old token file's value over instead, if it is still available and wasn't the reason for the rebuild.
6. **Clone and start**, as `deploy`: `git clone <repo> ~/jdad && cd ~/jdad && ./deploy/update-docker.sh`. The first run has no previous image to roll back to; if it fails, read the output and fix the cause (it prechecks the token file, the env file, the cert/key pair and modes before building). Later runs roll back to the previous image on a failed health check; an image from before the token file gets `JDAD_TOKEN` from the token file for that rollback only, and the checkout stays where it is (README, "Rolling back across the migration").
7. **Host firewall**, as root: `sudo ./deploy/firewall-cloudflare.sh apply --dry-run`, then `sudo ./deploy/firewall-cloudflare.sh install`, then `sudo jdad-firewall status`.
8. **DNS**: point `jdad-mcp.jondevs.com` at the new IP (keep it proxied). Check that the Configuration Rule still shows Full (strict).
9. **Verify:**
   - `curl -fsS --cacert ~/.config/jdad/tls/origin.crt --resolve jdad-mcp.jondevs.com:443:127.0.0.1 https://jdad-mcp.jondevs.com/healthz` on the host.
   - `curl -fsS https://jdad-mcp.jondevs.com/healthz` from anywhere.
   - One authenticated `tools/call kb_version` through the public URL, whose SHA matches `main`.
   - From outside Cloudflare, a TCP connect to the new IP on 443 times out.
10. **Clients**: if the token changed, update every host's token (see [token rotation](token-rotation.md)). Then destroy the old droplet, after taking a snapshot if it may hold evidence.

## NetBird on the current droplet (kept stopped)

The droplet also has a NetBird self-hosted stack: `netbird-proxy`, `netbird-traefik`, `netbird-server` and `netbird-dashboard`, all "Exited (0)" since the JDAD deploy (P0.5 evidence). Jon decided on 2026-11-22 to **keep it stopped, not removed**. It isn't part of JDAD and isn't covered by this repo's tests.

The risk is that a container with restart policy `always` comes back after a reboot or a Docker restart. `netbird-traefik` would then compete for 443 (the container start would fail, or JDAD's would) and could open 80. Check once, and after any change to that stack:

```bash
docker inspect -f '{{.Name}} restart={{.HostConfig.RestartPolicy.Name}} ports={{json .HostConfig.PortBindings}}' \
  netbird-proxy netbird-traefik netbird-server netbird-dashboard
```

Any `restart=always` or `restart=unless-stopped` on a container that was stopped by hand: `docker update --restart=no <name>`. A container stopped with `docker stop` stays stopped under `unless-stopped`, but `always` restarts it when the Docker daemon starts. Then do one reboot test in a quiet window, and check `docker ps` shows only `jdad-jdad-1` running and `ss -ltn` shows nothing on 80.

## Monitoring

- `.github/workflows/uptime.yml` probes `https://jdad-mcp.jondevs.com/healthz` four times an hour from GitHub's network once the repo is public. A failure emails whoever last edited the workflow's schedule.
- A second, independent monitor is worth adding, because Actions schedules can be late or paused after 60 days without repo activity. Any free HTTP uptime service works: GET the URL above every 5 minutes, alert on non-200 or a body other than `{"status":"ok"}`. Jon or Daisy creates the account; no token is needed, and none should be given to it.
- Neither monitor tests authentication. An authenticated synthetic check would mean handing a third party the token; don't.
