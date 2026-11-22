#!/usr/bin/env bash
# Build and run the JDAD image when Docker is available. Skip otherwise.
# Covers compose project/context, .dockerignore canary, TLS health/auth/Host
# checks, the README install path vs update-docker.sh, and cleanup.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "skip docker image tests: docker is not available on this box"
  exit 0
fi

SHA="$(git -C "$ROOT" rev-parse HEAD)"
WORKDIR="$(mktemp -d /tmp/jdad-docker-test.XXXXXX)"
TESTHOME="$WORKDIR/home"
CANARY_ENV="$ROOT/src/jdad/.env"
CANARY_KEY="$ROOT/practices/canary.key"
CLEANED=0

cleanup() {
  if [[ "$CLEANED" -eq 1 ]]; then
    return
  fi
  CLEANED=1
  if [[ -d "$TESTHOME" ]]; then
    HOME="$TESTHOME" JDAD_GIT_SHA="$SHA" JDAD_UID="$(id -u)" JDAD_GID="$(id -g)" \
      docker compose -f "$ROOT/deploy/docker-compose.yml" down --remove-orphans >/dev/null 2>&1 || true
  fi
  docker rm -f jdad-token-quote >/dev/null 2>&1 || true
  docker rm -f jdad-canary-ctr >/dev/null 2>&1 || true
  docker image rm -f \
    "jdad:${SHA}" \
    "jdad:previous" \
    "jdad:unknown" \
    "jdad:test" \
    "jdad-canary" >/dev/null 2>&1 || true
  rm -f "$CANARY_ENV" "$CANARY_KEY"
  rm -rf "$WORKDIR"
}

trap cleanup EXIT

mkdir -p "$TESTHOME/.config/jdad/tls"

# --- compose config: README install and update-docker.sh share project/context
{
  printf 'JDAD_TOKEN='
  openssl rand -hex 32
  printf 'JDAD_ALLOWED_HOSTS=jdad-mcp.jondevs.com\n'
} > "$TESTHOME/.config/jdad/jdad.env"
chmod 600 "$TESTHOME/.config/jdad/jdad.env"

# Placeholder files so `compose config` can resolve the volume; replaced
# with a real self-signed cert before `up`.
: > "$TESTHOME/.config/jdad/tls/origin.crt"
: > "$TESTHOME/.config/jdad/tls/origin.key"
chmod 600 "$TESTHOME/.config/jdad/tls/origin.key"

export HOME="$TESTHOME"
export JDAD_GIT_SHA="$SHA"
export JDAD_UID
export JDAD_GID
JDAD_UID="$(id -u)"
JDAD_GID="$(id -g)"
export JDAD_UID JDAD_GID

readme_json="$(docker compose -f "$ROOT/deploy/docker-compose.yml" config --format json)"
# Same command update-docker.sh uses after dropping --project-directory:
# cd repo root, -f deploy/docker-compose.yml (no --project-directory).
script_json="$(
  cd "$ROOT"
  docker compose -f "$ROOT/deploy/docker-compose.yml" config --format json
)"

python3 - "$ROOT" "$readme_json" "$script_json" << 'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
readme = json.loads(sys.argv[2])
script = json.loads(sys.argv[3])
for label, cfg in (("readme", readme), ("script", script)):
    name = cfg.get("name")
    svc = cfg.get("services", {}).get("jdad", {})
    build = svc.get("build") or {}
    context = Path(build.get("context") or "").resolve()
    if name != "jdad":
        sys.exit(f"FAIL {label} compose project name is {name!r}, expected 'jdad'")
    if context != root:
        sys.exit(f"FAIL {label} build context is {context}, expected {root}")
if readme["name"] != script["name"]:
    sys.exit("FAIL readme and update-docker.sh compose projects differ")
print("ok compose project name is jdad and context is the repo for both commands")
PY

# --- canary: stray env/key under src/ and practices/ must not be in the image
printf 'CANARY_SHOULD_NOT_BE_IN_IMAGE=1\n' > "$CANARY_ENV"
printf 'CANARY_KEY_MATERIAL=1\n' > "$CANARY_KEY"
docker build -t jdad-canary --build-arg JDAD_GIT_SHA=canary "$ROOT" >/dev/null
docker create --name jdad-canary-ctr jdad-canary >/dev/null
if docker export jdad-canary-ctr | tar -t | grep -E '(^|/)\.env$|(^|/)canary\.key$'; then
  echo "FAIL canary secret files were baked into the image" >&2
  exit 1
fi
docker rm jdad-canary-ctr >/dev/null
docker image rm -f jdad-canary >/dev/null
rm -f "$CANARY_ENV" "$CANARY_KEY"
echo "ok dockerignore canary (.env and *.key not in image)"

# --- literal quoted token is treated as unset (docker run --env)
docker build -t "jdad:test" --build-arg JDAD_GIT_SHA="$SHA" "$ROOT" >/dev/null
if docker run --rm --name jdad-token-quote \
  -e JDAD_TOKEN='""' \
  -e JDAD_ALLOWED_HOSTS=jdad-mcp.jondevs.com \
  "jdad:test" >/dev/null 2>"$WORKDIR/quote.err"; then
  echo "FAIL docker run with JDAD_TOKEN=\"\" should have refused to start" >&2
  cat "$WORKDIR/quote.err" >&2
  exit 1
fi
if ! grep -q "refusing to bind 0.0.0.0 without JDAD_TOKEN" "$WORKDIR/quote.err"; then
  echo "FAIL expected bind refusal in logs:" >&2
  cat "$WORKDIR/quote.err" >&2
  exit 1
fi
echo "ok docker run treats JDAD_TOKEN=\"\" as unset"

# venv is root-owned
owner="$(docker run --rm --user 0 --entrypoint stat "jdad:test" -c '%u' /app/.venv)"
if [[ "$owner" != 0 ]]; then
  echo "FAIL /app/.venv owner is uid $owner, expected 0" >&2
  exit 1
fi
echo "ok /app/.venv is root-owned"

# /app must be traversable by the compose uid (not only uid 999).
app_mode="$(docker run --rm --user 0 --entrypoint stat "jdad:test" -c '%a' /app)"
if [ "$app_mode" != "755" ]; then
  echo "FAIL /app mode is $app_mode, expected 755 so the compose uid can exec jdad-mcp" >&2
  exit 1
fi
if ! docker run --rm --user "$(id -u):$(id -g)" --entrypoint /bin/sh "jdad:test" -c 'command -v jdad-mcp >/dev/null'; then
  echo "FAIL compose uid cannot execute jdad-mcp (is /app mode 0700?)" >&2
  exit 1
fi
echo "ok /app is traversable and the compose uid can exec jdad-mcp"

# --- self-signed Origin cert and first-install + update-docker.sh
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -days 1 -nodes \
  -keyout "$TESTHOME/.config/jdad/tls/origin.key" \
  -out "$TESTHOME/.config/jdad/tls/origin.crt" \
  -subj "/CN=jdad-mcp.jondevs.com" >/dev/null 2>&1
chmod 600 "$TESTHOME/.config/jdad/tls/origin.key"
chmod 644 "$TESTHOME/.config/jdad/tls/origin.crt"

# Exact README install path (plus the required JDAD_GIT_SHA / UID for this tree).
docker compose -f "$ROOT/deploy/docker-compose.yml" up -d --build

# Wait for https://127.0.0.1/healthz (host 443 -> container 8443)
ok=0
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  if curl -fsSk --max-time 3 https://127.0.0.1/healthz >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  echo "FAIL compose install did not become healthy on https://127.0.0.1/healthz" >&2
  docker compose -f "$ROOT/deploy/docker-compose.yml" logs >&2 || true
  exit 1
fi

health="$(curl -sSk -o "$WORKDIR/health.body" -w '%{http_code}' https://127.0.0.1/healthz)"
body="$(cat "$WORKDIR/health.body")"
if [[ "$health" != 200 || "$body" != '{"status":"ok"}' ]]; then
  echo "FAIL https /healthz: status=$health body=$body" >&2
  exit 1
fi
echo "ok https://127.0.0.1/healthz 200"

project="$(docker compose -f "$ROOT/deploy/docker-compose.yml" ps --format json | python3 -c 'import json,sys; rows=[json.loads(l) for l in sys.stdin if l.strip()]; print(rows[0].get("Project","") if rows else "")')"
if [[ "$project" != jdad ]]; then
  echo "FAIL README install compose project is ${project!r}, expected jdad" >&2
  exit 1
fi
echo "ok README install project is jdad"

init='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"jdad-docker-tests","version":"0"}}}'
token="$(python3 -c 'from pathlib import Path; t=Path("'"$TESTHOME"'/.config/jdad/jdad.env").read_text(); print([l.split("=",1)[1].strip() for l in t.splitlines() if l.startswith("JDAD_TOKEN=")][0])')"
hdrs=(-H 'Accept: application/json, text/event-stream' -H 'Content-Type: application/json')

unauth="$(curl -sSk -o /dev/null -w '%{http_code}' -X POST https://127.0.0.1/mcp "${hdrs[@]}" --data "$init")"
if [[ "$unauth" != 401 ]]; then
  echo "FAIL /mcp without token: $unauth" >&2
  exit 1
fi
echo "ok https /mcp 401 without token"

authed="$(curl -sSk -o "$WORKDIR/mcp.ok" -w '%{http_code}' -X POST https://127.0.0.1/mcp \
  "${hdrs[@]}" -H "Authorization: Bearer $token" -H "Host: jdad-mcp.jondevs.com" \
  --data "$init")"
if [[ "$authed" != 200 ]]; then
  echo "FAIL /mcp with token and listed Host: $authed" >&2
  cat "$WORKDIR/mcp.ok" >&2 || true
  exit 1
fi
echo "ok https /mcp 200 with token and Host: jdad-mcp.jondevs.com"

badhost="$(curl -sSk -o /dev/null -w '%{http_code}' -X POST https://127.0.0.1/mcp \
  "${hdrs[@]}" -H "Authorization: Bearer $token" -H "Host: not-listed.example" \
  --data "$init")"
if [[ "$badhost" != 421 ]]; then
  echo "FAIL /mcp unlisted Host: $badhost" >&2
  exit 1
fi
echo "ok https /mcp 421 with unlisted Host"

# kb_version SHA is the baked git SHA
curl -sSk -D "$WORKDIR/mcp.hdrs" -o /dev/null -X POST https://127.0.0.1/mcp \
  "${hdrs[@]}" -H "Authorization: Bearer $token" -H "Host: jdad-mcp.jondevs.com" \
  --data "$init"
session="$(awk -F': ' 'tolower($1)=="mcp-session-id"{gsub(/\r/,"",$2); print $2}' "$WORKDIR/mcp.hdrs")"
kb_body="$(curl -sSk -X POST https://127.0.0.1/mcp \
  "${hdrs[@]}" -H "Authorization: Bearer $token" -H "Host: jdad-mcp.jondevs.com" \
  -H "Mcp-Session-Id: $session" \
  --data '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"kb_version","arguments":{}}}')"
python3 - "$kb_body" "$SHA" << 'PY'
import json, sys
raw, sha = sys.argv[1], sys.argv[2]
# SSE or JSON
text = raw
if "data:" in raw:
    lines = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")]
    text = lines[-1] if lines else raw
msg = json.loads(text)
result = msg.get("result") or {}
# structuredContent or content text
payload = result.get("structuredContent") or result
if isinstance(payload, dict) and "result" in payload and "sha" not in payload:
    payload = payload["result"]
if not isinstance(payload, dict) or "sha" not in payload:
    # try content
    for block in result.get("content") or []:
        if block.get("type") == "text":
            payload = json.loads(block["text"])
            break
if not isinstance(payload, dict) or payload.get("sha") != sha:
    sys.exit(f"FAIL kb_version sha={payload!r}, expected {sha}")
print(f"ok kb_version sha={sha}")
PY

# update-docker.sh end-to-end (already up to date) must stay on project jdad
if ! HOME="$TESTHOME" JDAD_UID="$JDAD_UID" JDAD_GID="$JDAD_GID" \
  JDAD_SKIP_GIT_PULL=1 \
  "$ROOT/deploy/update-docker.sh"; then
  echo "FAIL update-docker.sh on an up-to-date checkout" >&2
  exit 1
fi
project2="$(docker compose -f "$ROOT/deploy/docker-compose.yml" ps --format json | python3 -c 'import json,sys; rows=[json.loads(l) for l in sys.stdin if l.strip()]; print(rows[0].get("Project","") if rows else "")')"
if [[ "$project2" != jdad ]]; then
  echo "FAIL update-docker.sh compose project is ${project2!r}, expected jdad" >&2
  exit 1
fi
echo "ok update-docker.sh stayed on project jdad"

# rollback: force a failed health check, previous image should come back
if HOME="$TESTHOME" JDAD_UID="$JDAD_UID" JDAD_GID="$JDAD_GID" \
  JDAD_SKIP_GIT_PULL=1 \
  JDAD_HEALTH_URL="https://127.0.0.1:1/healthz" \
  "$ROOT/deploy/update-docker.sh"; then
  echo "FAIL update-docker.sh should have failed with a bad HEALTH_URL" >&2
  exit 1
fi
if ! curl -fsSk --max-time 5 https://127.0.0.1/healthz >/dev/null; then
  echo "FAIL service was not rolled back to a healthy state" >&2
  exit 1
fi
echo "ok update-docker.sh rolls back when the health check fails"
