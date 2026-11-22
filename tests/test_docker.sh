#!/usr/bin/env bash
# Build and run the JDAD image when Docker is available. Skip otherwise.
# Covers compose project/context, .dockerignore canary, TLS health/auth/Host
# checks, update-docker.sh (up to date, pruning, prechecks, and a real
# rollback from a deliberately broken commit), and cleanup.
#
# Isolation: everything runs under a unique compose project
# (jdad-test-<pid>), a unique image repo with the same name, and an
# ephemeral loopback port, so it cannot stop the production project
# "jdad", take port 443, or delete its rollback image. It refuses to run
# at all if a compose project named "jdad" exists on this daemon.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "skip docker image tests: docker is not available on this box"
  exit 0
fi

if [[ -n "$(docker ps -a -q --filter label=com.docker.compose.project=jdad)" ]]; then
  echo "FAIL refusing to run: compose project 'jdad' has containers on this daemon (production?)." >&2
  echo "     These tests never touch it, but run them on a daemon without the real deploy." >&2
  exit 1
fi

SHA="$(git -C "$ROOT" rev-parse HEAD)"
TAG_ID="jdad-test-$$"
PROJECT="$TAG_ID"
IMG="$TAG_ID"
CANARY_IMG="$TAG_ID-canary"
WORKDIR="$(mktemp -d "/tmp/$TAG_ID.XXXXXX")"
TESTHOME="$WORKDIR/home"
CANARY_ENV="$ROOT/src/jdad/.env"
CANARY_KEY="$ROOT/practices/canary.key"
CLEANED=0

export JDAD_COMPOSE_PROJECT="$PROJECT"
export JDAD_IMAGE_REPO="$IMG"
export JDAD_PUBLISH="127.0.0.1:"   # ephemeral loopback host port
unset JDAD_HEALTH_URL
COMPOSE=(docker compose -p "$PROJECT" -f "$ROOT/deploy/docker-compose.yml")

cleanup() {
  if [[ "$CLEANED" -eq 1 ]]; then
    return
  fi
  CLEANED=1
  if [[ -d "$TESTHOME" ]]; then
    HOME="$TESTHOME" JDAD_GIT_SHA="$SHA" JDAD_UID="$(id -u)" JDAD_GID="$(id -g)" \
      "${COMPOSE[@]}" down --remove-orphans >/dev/null 2>&1 || true
  fi
  docker rm -f "$TAG_ID-token-quote" "$TAG_ID-canary-ctr" >/dev/null 2>&1 || true
  local refs
  refs="$(docker image ls --format '{{.Repository}}:{{.Tag}}' | grep -E "^($IMG|$CANARY_IMG):" || true)"
  if [[ -n "$refs" ]]; then
    # shellcheck disable=SC2086
    docker image rm -f $refs >/dev/null 2>&1 || true
  fi
  rm -f "$CANARY_ENV" "$CANARY_KEY"
  rm -rf "$WORKDIR"
}

trap cleanup EXIT

mkdir -p "$TESTHOME/.config/jdad/tls"

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
JDAD_UID="$(id -u)"
JDAD_GID="$(id -g)"
export JDAD_UID JDAD_GID

# --- compose config: the file itself names project jdad and the repo as
# context (README install and update-docker.sh both rely on that). This
# only renders config; it starts nothing. Its output contains JDAD_TOKEN,
# so it is parsed here and never printed.
readme_json="$(docker compose -f "$ROOT/deploy/docker-compose.yml" config --format json)"
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

# Without overrides the file still publishes 443 and tags jdad:<sha>.
default_json="$(env -u JDAD_PUBLISH -u JDAD_IMAGE_REPO docker compose -f "$ROOT/deploy/docker-compose.yml" config --format json)"
python3 - "$default_json" "$SHA" << 'PY'
import json, sys
cfg = json.loads(sys.argv[1]); svc = cfg["services"]["jdad"]
ports = svc.get("ports") or []
if not any(str(p.get("published")) == "443" and p.get("target") == 8443 for p in ports):
    sys.exit(f"FAIL default ports are {ports!r}, expected 443:8443")
if svc.get("image") != f"jdad:{sys.argv[2]}":
    sys.exit(f"FAIL default image is {svc.get('image')!r}")
print("ok defaults: publishes 443:8443 and tags jdad:<sha>")
PY

# --- canary: stray env/key under src/ and practices/ must not be in the image
printf 'CANARY_SHOULD_NOT_BE_IN_IMAGE=1\n' > "$CANARY_ENV"
printf 'CANARY_KEY_MATERIAL=1\n' > "$CANARY_KEY"
docker build -t "$CANARY_IMG" --build-arg JDAD_GIT_SHA=canary "$ROOT" >/dev/null
docker create --name "$TAG_ID-canary-ctr" "$CANARY_IMG" >/dev/null
if docker export "$TAG_ID-canary-ctr" | tar -t | grep -E '(^|/)\.env$|(^|/)canary\.key$'; then
  echo "FAIL canary secret files were baked into the image" >&2
  exit 1
fi
docker rm "$TAG_ID-canary-ctr" >/dev/null
docker image rm -f "$CANARY_IMG" >/dev/null
rm -f "$CANARY_ENV" "$CANARY_KEY"
echo "ok dockerignore canary (.env and *.key not in image)"

# --- literal quoted token is treated as unset (docker run --env)
docker build -t "$IMG:test" --build-arg JDAD_GIT_SHA="$SHA" "$ROOT" >/dev/null
if docker run --rm --name "$TAG_ID-token-quote" \
  -e JDAD_TOKEN='""' \
  -e JDAD_ALLOWED_HOSTS=jdad-mcp.jondevs.com \
  "$IMG:test" >/dev/null 2>"$WORKDIR/quote.err"; then
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

owner="$(docker run --rm --user 0 --entrypoint stat "$IMG:test" -c '%u' /app/.venv)"
if [[ "$owner" != 0 ]]; then
  echo "FAIL /app/.venv owner is uid $owner, expected 0" >&2
  exit 1
fi
echo "ok /app/.venv is root-owned"

app_mode="$(docker run --rm --user 0 --entrypoint stat "$IMG:test" -c '%a' /app)"
if [ "$app_mode" != "755" ]; then
  echo "FAIL /app mode is $app_mode, expected 755 so the compose uid can exec jdad-mcp" >&2
  exit 1
fi
if ! docker run --rm --user "$(id -u):$(id -g)" --entrypoint /bin/sh "$IMG:test" -c 'command -v jdad-mcp >/dev/null'; then
  echo "FAIL compose uid cannot execute jdad-mcp (is /app mode 0700?)" >&2
  exit 1
fi
echo "ok /app is traversable and the compose uid can exec jdad-mcp"

# --- self-signed Origin cert, then the README install (isolated project)
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -days 1 -nodes \
  -keyout "$TESTHOME/.config/jdad/tls/origin.key" \
  -out "$TESTHOME/.config/jdad/tls/origin.crt" \
  -subj "/CN=jdad-mcp.jondevs.com" >/dev/null 2>&1
chmod 600 "$TESTHOME/.config/jdad/tls/origin.key"
chmod 644 "$TESTHOME/.config/jdad/tls/origin.crt"

"${COMPOSE[@]}" up -d --build

base_url() {
  local mapped
  mapped="$("${COMPOSE[@]}" port jdad 8443 2>/dev/null | head -n1 || true)"
  [[ -n "$mapped" ]] || return 1
  printf 'https://127.0.0.1:%s\n' "${mapped##*:}"
}

wait_healthy() {
  local base
  for _ in $(seq 1 30); do
    if base="$(base_url)" && curl -fsSk --max-time 3 "$base/healthz" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

running_image() {
  local cid
  cid="$("${COMPOSE[@]}" ps -q jdad)"
  docker inspect -f '{{.Config.Image}}' "$cid"
}

if ! wait_healthy; then
  echo "FAIL compose install did not become healthy on its loopback port" >&2
  "${COMPOSE[@]}" logs >&2 || true
  exit 1
fi
BASE="$(base_url)"
case "$BASE" in
  https://127.0.0.1:443) echo "FAIL test published on 443; expected an ephemeral port" >&2; exit 1 ;;
esac
published="$(docker port "$("${COMPOSE[@]}" ps -q jdad)" 8443/tcp)"
if grep -qv '^127\.0\.0\.1:' <<<"$published"; then
  echo "FAIL test container is published beyond loopback: $published" >&2
  exit 1
fi
echo "ok isolated project $PROJECT on loopback ephemeral port ${BASE##*:}"

health="$(curl -sSk -o "$WORKDIR/health.body" -w '%{http_code}' "$BASE/healthz")"
body="$(cat "$WORKDIR/health.body")"
if [[ "$health" != 200 || "$body" != '{"status":"ok"}' ]]; then
  echo "FAIL https /healthz: status=$health body=$body" >&2
  exit 1
fi
echo "ok https /healthz 200"

init='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"jdad-docker-tests","version":"0"}}}'
token="$(python3 -c 'from pathlib import Path; t=Path("'"$TESTHOME"'/.config/jdad/jdad.env").read_text(); print([l.split("=",1)[1].strip() for l in t.splitlines() if l.startswith("JDAD_TOKEN=")][0])')"
hdrs=(-H 'Accept: application/json, text/event-stream' -H 'Content-Type: application/json')

unauth="$(curl -sSk -o /dev/null -w '%{http_code}' -X POST "$BASE/mcp" "${hdrs[@]}" --data "$init")"
if [[ "$unauth" != 401 ]]; then
  echo "FAIL /mcp without token: $unauth" >&2
  exit 1
fi
echo "ok https /mcp 401 without token"

authed="$(curl -sSk -o "$WORKDIR/mcp.ok" -w '%{http_code}' -X POST "$BASE/mcp" \
  "${hdrs[@]}" -H "Authorization: Bearer $token" -H "Host: jdad-mcp.jondevs.com" \
  --data "$init")"
if [[ "$authed" != 200 ]]; then
  echo "FAIL /mcp with token and listed Host: $authed" >&2
  exit 1
fi
echo "ok https /mcp 200 with token and Host: jdad-mcp.jondevs.com"

badhost="$(curl -sSk -o /dev/null -w '%{http_code}' -X POST "$BASE/mcp" \
  "${hdrs[@]}" -H "Authorization: Bearer $token" -H "Host: not-listed.example" \
  --data "$init")"
if [[ "$badhost" != 421 ]]; then
  echo "FAIL /mcp unlisted Host: $badhost" >&2
  exit 1
fi
echo "ok https /mcp 421 with unlisted Host"

# kb_version SHA is the baked git SHA
check_kb_sha() {
  local base="$1" want="$2" session kb_body
  curl -sSk -D "$WORKDIR/mcp.hdrs" -o /dev/null -X POST "$base/mcp" \
    "${hdrs[@]}" -H "Authorization: Bearer $token" -H "Host: jdad-mcp.jondevs.com" \
    --data "$init"
  session="$(awk -F': ' 'tolower($1)=="mcp-session-id"{gsub(/\r/,"",$2); print $2}' "$WORKDIR/mcp.hdrs")"
  kb_body="$(curl -sSk -X POST "$base/mcp" \
    "${hdrs[@]}" -H "Authorization: Bearer $token" -H "Host: jdad-mcp.jondevs.com" \
    -H "Mcp-Session-Id: $session" \
    --data '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"kb_version","arguments":{}}}')"
  python3 - "$kb_body" "$want" << 'PY'
import json, sys
raw, sha = sys.argv[1], sys.argv[2]
text = raw
if "data:" in raw:
    lines = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")]
    text = lines[-1] if lines else raw
msg = json.loads(text)
result = msg.get("result") or {}
payload = result.get("structuredContent") or result
if isinstance(payload, dict) and "result" in payload and "sha" not in payload:
    payload = payload["result"]
if not isinstance(payload, dict) or "sha" not in payload:
    for block in result.get("content") or []:
        if block.get("type") == "text":
            payload = json.loads(block["text"])
            break
if not isinstance(payload, dict) or payload.get("sha") != sha:
    sys.exit(f"FAIL kb_version sha={payload!r}, expected {sha}")
print(f"ok kb_version sha={sha}")
PY
}
check_kb_sha "$BASE" "$SHA"

# --- update-docker.sh runs from a scratch clone, so the rollback test can
# add a deliberately broken commit without touching this checkout. The
# clone gets this working tree (tracked + untracked, not ignored) as its
# "good" commit, so uncommitted script changes are what gets tested.
CLONE="$WORKDIR/repo"
git clone -q "$ROOT" "$CLONE"
git -C "$ROOT" ls-files -z -c -o --exclude-standard | (cd "$ROOT" && xargs -0 tar -cf - --) | tar -xf - -C "$CLONE"
git -C "$CLONE" add -A
if ! git -C "$CLONE" diff --cached --quiet; then
  git -C "$CLONE" -c user.name=jdad-test -c user.email=jdad-test@example.invalid \
    commit -q -m "test: working tree"
fi
GOOD="$(git -C "$CLONE" rev-parse HEAD)"

run_update() {
  HOME="$TESTHOME" JDAD_UID="${UPDATE_UID:-$JDAD_UID}" JDAD_GID="$JDAD_GID" \
    JDAD_SKIP_GIT_PULL=1 JDAD_GIT_SHA="" \
    "$CLONE/deploy/update-docker.sh"
}

# Old images that pruning must remove, and must not confuse with others.
STALE1="$IMG:$(printf '1%.0s' {1..40})"
STALE2="$IMG:$(printf '2%.0s' {1..40})"
docker tag "$IMG:$SHA" "$STALE1"
docker tag "$IMG:$SHA" "$STALE2"

if ! run_update > "$WORKDIR/update1.log" 2>&1; then
  echo "FAIL update-docker.sh on the good commit" >&2
  cat "$WORKDIR/update1.log" >&2
  exit 1
fi
project2="$("${COMPOSE[@]}" ps --format json | python3 -c 'import json,sys; rows=[json.loads(l) for l in sys.stdin if l.strip()]; print(rows[0].get("Project","") if rows else "")')"
if [[ "$project2" != "$PROJECT" ]]; then
  echo "FAIL update-docker.sh compose project is ${project2!r}, expected $PROJECT" >&2
  exit 1
fi
if [[ "$(running_image)" != "$IMG:$GOOD" ]]; then
  echo "FAIL after update, running image is $(running_image), expected $IMG:$GOOD" >&2
  exit 1
fi
echo "ok update-docker.sh stayed on project $PROJECT and runs $IMG:$GOOD"

for stale in "$STALE1" "$STALE2"; do
  if docker image inspect "$stale" >/dev/null 2>&1; then
    echo "FAIL prune left $stale" >&2
    exit 1
  fi
done
for kept in "$IMG:$GOOD" "$IMG:$SHA" "$IMG:previous"; do
  if ! docker image inspect "$kept" >/dev/null 2>&1; then
    echo "FAIL prune removed $kept (current/previous must stay)" >&2
    exit 1
  fi
done
echo "ok update-docker.sh pruned old sha tags and kept current + previous"

# --- prechecks refuse before touching the running service
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -days 1 -nodes \
  -keyout "$WORKDIR/other.key" -out "$WORKDIR/other.crt" -subj "/CN=other" >/dev/null 2>&1
chmod 600 "$WORKDIR/other.key"
if JDAD_SSL_KEYFILE_HOST="$WORKDIR/other.key" run_update > "$WORKDIR/mismatch.log" 2>&1; then
  echo "FAIL update-docker.sh accepted a key that does not match the cert" >&2
  exit 1
fi
grep -q "does not match the public key" "$WORKDIR/mismatch.log" || { cat "$WORKDIR/mismatch.log" >&2; echo "FAIL no mismatch message" >&2; exit 1; }
echo "ok precheck refuses a cert/key pair that does not match"

if UPDATE_UID=0 run_update > "$WORKDIR/root.log" 2>&1; then
  echo "FAIL update-docker.sh accepted JDAD_UID=0" >&2
  exit 1
fi
grep -q "refusing to run the container as root" "$WORKDIR/root.log" || { cat "$WORKDIR/root.log" >&2; echo "FAIL no uid 0 message" >&2; exit 1; }
if [[ "$(running_image)" != "$IMG:$GOOD" ]]; then
  echo "FAIL a refused precheck changed the running image" >&2
  exit 1
fi
echo "ok precheck refuses JDAD_UID=0 and leaves the service alone"

# --- real rollback: a broken commit, the real health URL (no override)
printf '\nraise SystemExit("deliberately broken build for the rollback test")\n' >> "$CLONE/src/jdad/server.py"
git -C "$CLONE" -c user.name=jdad-test -c user.email=jdad-test@example.invalid \
  commit -q -am "test: deliberately broken"
BROKEN="$(git -C "$CLONE" rev-parse HEAD)"

if run_update > "$WORKDIR/rollback.log" 2>&1; then
  echo "FAIL update-docker.sh reported success for a broken commit" >&2
  cat "$WORKDIR/rollback.log" >&2
  exit 1
fi
if ! grep -q "rolled back to $IMG:$GOOD and https://127.0.0.1:[0-9]*/healthz is ok" "$WORKDIR/rollback.log"; then
  echo "FAIL rollback did not report a healthy rollback to $IMG:$GOOD" >&2
  cat "$WORKDIR/rollback.log" >&2
  exit 1
fi
if ! docker image inspect "$IMG:$BROKEN" >/dev/null 2>&1; then
  echo "FAIL the broken image $IMG:$BROKEN was never built" >&2
  exit 1
fi
if [[ "$(running_image)" != "$IMG:$GOOD" ]]; then
  echo "FAIL after rollback, running image is $(running_image), expected $IMG:$GOOD" >&2
  exit 1
fi
wait_healthy || { echo "FAIL service not healthy after rollback" >&2; exit 1; }
check_kb_sha "$(base_url)" "$GOOD"
echo "ok update-docker.sh rolls back a broken commit to $IMG:$GOOD"
