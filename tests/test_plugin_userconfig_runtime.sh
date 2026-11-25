#!/usr/bin/env bash
# Opt-in runtime proof for roadmap P3.7 (not part of ./verify: needs Docker
# and network access to npm). Everything runs in throwaway containers on a
# private Docker network, so nothing touches this machine's Claude Code
# config, keychain or the production endpoint:
#
#   server: an image built from this checkout, JDAD_TOKEN = an ephemeral
#           token generated for this run
#   client: node + the pinned Claude Code CLI, with a copy of this plugin
#           whose URL points at the server container
#
# For each case, `claude mcp list` health-checks the plugin's server and the
# server's access log records the HTTP status. The token never prints; the
# script greps the client output and the server logs for it at the end.
#
#   bash tests/test_plugin_userconfig_runtime.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLAUDE_VERSION="${JDAD_TEST_CLAUDE_VERSION:-2.1.330}"
ID="jdad-p37-$(date +%s)-$$"
NET="$ID-net"
SRV="$ID-srv"
CLI="$ID-cli"
IMG="$ID-img"
WORK="$(mktemp -d)"
TOKEN="$(openssl rand -hex 24)"

cleanup() {
  docker rm -f "$SRV" "$CLI" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  docker image rm -f "$IMG" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

fail() { echo "FAIL $*" >&2; exit 1; }

docker network create "$NET" >/dev/null
docker build -q -t "$IMG" "$ROOT" >/dev/null
docker run -d --name "$SRV" --network "$NET" \
  -e JDAD_TOKEN="$TOKEN" -e JDAD_ALLOWED_HOSTS="$SRV" \
  "$IMG" jdad-mcp --http --host 0.0.0.0 --port 8765 >/dev/null

# A copy of the plugin (manifest, marketplace, MCP config) pointed at the server.
mkdir -p "$WORK/plugin/.claude-plugin"
cp "$ROOT/.claude-plugin/plugin.json" "$ROOT/.claude-plugin/marketplace.json" "$WORK/plugin/.claude-plugin/"
sed "s|https://jdad-mcp.jondevs.com/mcp|http://$SRV:8765/mcp|" "$ROOT/.mcp.json" > "$WORK/plugin/.mcp.json"
grep -q "http://$SRV:8765/mcp" "$WORK/plugin/.mcp.json" || fail "could not point the plugin copy at the test server"

docker run -d --name "$CLI" --network "$NET" -v "$WORK/plugin:/plugin:ro" \
  node:22-slim sleep 900 >/dev/null
docker exec "$CLI" sh -c "npm install -g --silent @anthropic-ai/claude-code@$CLAUDE_VERSION >/dev/null 2>&1" \
  || fail "could not install @anthropic-ai/claude-code@$CLAUDE_VERSION"
in_cli() { docker exec -i -e HOME=/root "$CLI" "$@"; }
in_cli claude --version
in_cli claude plugin marketplace add /plugin >/dev/null
in_cli claude plugin install jdad@jdad >/dev/null

status() {  # the plugin server's line from `claude mcp list`
  in_cli claude mcp list 2>&1 | grep -i jdad || true
}
log_mark() { docker logs "$SRV" 2>&1 | wc -l; }
statuses_since() { docker logs "$SRV" 2>&1 | tail -n +"$(( $1 + 1 ))" | grep -oE '"(GET|POST|DELETE) /mcp HTTP/1.1" [0-9]+' | awk '{print $NF}' | sort | uniq -c | tr '\n' ' '; }

echo "== 1. token not configured"
mark="$(log_mark)"
unset_line="$(status)"
echo "mcp list: $unset_line"
echo "server saw: $(statuses_since "$mark")"
[[ "$unset_line" != *"Connected"* ]] || fail "connected without a token"

echo "== 2. wrong token"
printf '{"jdad_token":"wrong-%s"}\n' "$(openssl rand -hex 4)" | in_cli claude plugin configure jdad@jdad --values-stdin >/dev/null
mark="$(log_mark)"
wrong_line="$(status)"
echo "mcp list: $wrong_line"
echo "server saw: $(statuses_since "$mark")"
[[ "$wrong_line" != *"Connected"* ]] || fail "connected with a wrong token"

echo "== 3. right token"
printf '{"jdad_token":"%s"}\n' "$TOKEN" | in_cli claude plugin configure jdad@jdad --values-stdin >/dev/null
mark="$(log_mark)"
right_line="$(status)"
echo "mcp list: $right_line"
echo "server saw: $(statuses_since "$mark")"
[[ "$right_line" == *"Connected"* ]] || fail "not connected with the right token"

echo "== 4. where the value is stored (sensitive: not in settings.json)"
if in_cli sh -c 'cat /root/.claude/settings.json 2>/dev/null' | grep -qF "$TOKEN"; then
  fail "the sensitive token is in settings.json"
fi
echo "settings.json does not contain the token"
shown="$(in_cli claude plugin configure jdad@jdad --json 2>&1)"
if grep -qF "$TOKEN" <<<"$shown"; then fail "claude plugin configure --json printed the sensitive token"; fi
grep -q '"configured"' <<<"$shown" && grep -A2 '"configured"' <<<"$shown" | grep -q jdad_token \
  || fail "jdad_token is not reported as configured"
echo "configure --json: jdad_token configured, value not shown"

echo "== 5. documented env fallback: a user-scope entry reading \$JDAD_TOKEN"
in_cli claude mcp add --scope user --transport http jdad-env "http://$SRV:8765/mcp" \
  --header 'Authorization: Bearer ${JDAD_TOKEN}' >/dev/null
env_line="$(docker exec -e HOME=/root -e JDAD_TOKEN="$TOKEN" "$CLI" claude mcp list 2>&1 | grep 'jdad-env' || true)"
echo "mcp list: $env_line"
[[ "$env_line" == *"Connected"* ]] || fail "the documented user-scope env fallback did not connect"
if in_cli sh -c 'cat /root/.claude.json 2>/dev/null' | grep -qF "$TOKEN"; then
  fail "the env fallback wrote the token value into ~/.claude.json"
fi
echo "ok: ~/.claude.json holds the \${JDAD_TOKEN} reference, not the value"

echo "== 6. the token never appears in output or server logs"
if docker logs "$SRV" 2>&1 | grep -qF "$TOKEN"; then fail "token in server logs"; fi
echo "ok: token not in server logs"
echo "ok P3.7 runtime: unset and wrong tokens don't connect; the configured token connects; the env fallback works"
