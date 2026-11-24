# Runbook: rotate the bearer token

When to use this: on a schedule (suggested: every 90 days), when a host that holds the token is retired or lost, or when the token may have been exposed (pasted, logged, committed). Roadmap P0.9, JON-1344. This assumes the token-file deploy from PR #9 (`~/.config/jdad/token`, mounted as a compose secret).

There is one shared token, and the server accepts only one at a time. Every client stops working at the restart in step 3 until it gets the new value. Do it when you can update the clients straight away.

## Steps (on the droplet, as the deploy user)

1. **List the clients first**: every host and agent config that sends `Authorization: Bearer` to `https://jdad-mcp.jondevs.com/mcp`. That means the Claude Code plugin hosts (the plugin's `jdad_token` option from 0.8.0: `/config` or `claude plugin configure jdad@jdad --values-stdin`, see the README; `JDAD_TOKEN` in the environment for a `jdad-env` user-scope entry or a pre-0.8.0 plugin), Codex (`bearer_token_env_var`), Cursor and Grok Build configs, and any scripts.
2. **Write the new token** without printing it:

   ```bash
   chmod 600 ~/.config/jdad/token
   (umask 077 && openssl rand -hex 32 > ~/.config/jdad/token)
   chmod 400 ~/.config/jdad/token
   ```

3. **Restart** so the server reads it (no rebuild needed):

   ```bash
   cd ~/jdad && docker compose -p jdad -f deploy/docker-compose.yml restart jdad
   ```

   Or run `./deploy/update-docker.sh`, which also pulls `main`, so only do that if you mean to deploy too.
4. **Check** (counts and status codes only):

   ```bash
   curl -fsS --cacert ~/.config/jdad/tls/origin.crt --resolve jdad-mcp.jondevs.com:443:127.0.0.1 https://jdad-mcp.jondevs.com/healthz
   # the old token now gets 401 and the new one 200, e.g. an initialize call with each,
   # reading the values from files, never typing or echoing them
   ```

5. **Hand the new value to each client** over a channel that doesn't keep it (a password manager share, or an SSH session that writes it straight into the client host's secret store). Never paste it into chat, tickets, PRs or Linear.
6. **Update every client** from step 1 and confirm each one connects (for example `kb_version` from each agent).
7. **Note it** on the card: the date, the reason, and which clients were updated. Never record the value.

## Exposure response

If the token was exposed, do steps 2 to 4 first and the client updates after, accepting the downtime. Then check the access logs for use of the old token (`docker logs jdad-jdad-1 --since <time>`: look for 200s on `/mcp` from unfamiliar addresses). With the host firewall on, all traffic comes through Cloudflare, so the Cloudflare dashboard shows the real client IPs.

## Later

A second accepted token during rotation (no flag day) is tracked as an idea in the red-team review (M1). Token entry through the plugin's `userConfig` is P3.7 (0.8.0).
