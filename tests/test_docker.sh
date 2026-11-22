#!/usr/bin/env bash
# Build and run the JDAD image when Docker is available. Skip otherwise.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "skip docker image tests: docker is not available on this box"
  exit 0
fi

TOKEN="test-jdad-token-not-a-secret"
IMAGE="jdad:test"
NAME="jdad-test-$$"
cid=""
cleanup() {
  if [[ -n "$cid" ]]; then
    docker rm -f "$cid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

docker build -t "$IMAGE" "$ROOT"

cid="$(docker run -d --rm \
  -e "JDAD_TOKEN=$TOKEN" \
  -e "JDAD_ALLOWED_HOSTS=jdad-mcp.jondevs.com" \
  -p 127.0.0.1::8765 \
  --read-only --tmpfs /tmp --cap-drop ALL \
  --security-opt no-new-privileges:true \
  "$IMAGE")"

port="$(docker port "$cid" 8765/tcp | awk -F: 'NR==1{print $NF}')"
base="http://127.0.0.1:${port}"

ok=0
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if curl -fsS --max-time 3 "$base/healthz" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  echo "FAIL docker image did not become healthy" >&2
  docker logs "$cid" >&2 || true
  exit 1
fi

health="$(curl -sS -o /tmp/jdad-h.body -w '%{http_code}' "$base/healthz")"
body="$(cat /tmp/jdad-h.body)"
[[ "$health" == 200 && "$body" == '{"status":"ok"}' ]] || {
  echo "FAIL /healthz: status=$health body=$body" >&2
  exit 1
}
echo "ok docker /healthz 200"

init='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"jdad-docker-tests","version":"0"}}}'
hdrs=(-H 'Accept: application/json, text/event-stream' -H 'Content-Type: application/json')

unauth="$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$base/mcp" "${hdrs[@]}" --data "$init")"
[[ "$unauth" == 401 ]] || { echo "FAIL /mcp without token: $unauth" >&2; exit 1; }
echo "ok docker /mcp 401 without token"

authed="$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$base/mcp" \
  "${hdrs[@]}" -H "Authorization: Bearer $TOKEN" -H "Host: jdad-mcp.jondevs.com" \
  --data "$init")"
[[ "$authed" == 200 ]] || { echo "FAIL /mcp with token and listed Host: $authed" >&2; exit 1; }
echo "ok docker /mcp 200 with token and Host: jdad-mcp.jondevs.com"

badhost="$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$base/mcp" \
  "${hdrs[@]}" -H "Authorization: Bearer $TOKEN" -H "Host: not-listed.example" \
  --data "$init")"
[[ "$badhost" == 421 ]] || { echo "FAIL /mcp unlisted Host: $badhost" >&2; exit 1; }
echo "ok docker /mcp 421 with unlisted Host"
