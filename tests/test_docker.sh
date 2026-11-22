#!/usr/bin/env bash
# Build and run the JDAD image when Docker is available. Skip otherwise.
# Covers compose project/context, .dockerignore canary, TLS health/auth/Host
# checks, update-docker.sh (up to date, pruning, prechecks, and a real
# rollback from a deliberately broken commit), and cleanup.
#
# Isolation: everything runs under a unique compose project
# (jdad-test-<time>-<pid>-<random>), a unique image repo with the same
# name, and an ephemeral loopback port, so it cannot stop the production
# project "jdad", take port 443, or delete its rollback image. The time and
# random parts matter: two runs in different PID namespaces (containers,
# CI runners) on one daemon can have the same PID, and their cleanups
# would then remove each other's containers and images. It refuses to run
# at all if a compose project named "jdad" exists on this daemon.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# This script later points HOME at a scratch directory. Docker finds its CLI
# plugins (compose, on OrbStack and Docker Desktop) and the active context
# through ~/.docker, so pin DOCKER_CONFIG to the real one first; otherwise
# `docker compose` vanishes ("unknown shorthand flag: 'f' in -f").
export DOCKER_CONFIG="${DOCKER_CONFIG:-$HOME/.docker}"

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
TAG_ID="jdad-test-$(date +%s)-$$-$(printf '%04x%04x' "$RANDOM" "$RANDOM")"
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

printf 'JDAD_ALLOWED_HOSTS=jdad-mcp.jondevs.com\n' > "$TESTHOME/.config/jdad/jdad.env"
chmod 600 "$TESTHOME/.config/jdad/jdad.env"
# The token lives in its own 0400 file, mounted as a compose secret.
(umask 077 && openssl rand -hex 32 > "$TESTHOME/.config/jdad/token")
chmod 400 "$TESTHOME/.config/jdad/token"

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
mem = svc.get("mem_limit")
if str(mem) not in {"512m", str(512 * 1024 * 1024)}:
    sys.exit(f"FAIL mem_limit is {mem!r}, expected 512m")
if svc.get("pids_limit") != 256:
    sys.exit(f"FAIL pids_limit is {svc.get('pids_limit')!r}, expected 256")
if float(svc.get("cpus") or 0) != 1.0:
    sys.exit(f"FAIL cpus is {svc.get('cpus')!r}, expected 1.0")
log = svc.get("logging") or {}
opts = log.get("options") or {}
if log.get("driver") != "json-file" or opts.get("max-size") != "10m" or str(opts.get("max-file")) != "3":
    sys.exit(f"FAIL logging is {log!r}, expected json-file with max-size 10m, max-file 3")
print("ok limits: mem 512m, pids 256, cpus 1.0, json-file logs rotated at 10m x 3")
PY

# --- canary: stray env/key under src/ and practices/ must not be in the image
printf 'CANARY_SHOULD_NOT_BE_IN_IMAGE=1\n' > "$CANARY_ENV"
printf 'CANARY_KEY_MATERIAL=1\n' > "$CANARY_KEY"
# Build through compose (BuildKit) rather than `docker build`: this daemon
# has no buildx, so the legacy builder would leave dangling stage images.
JDAD_IMAGE_REPO="$CANARY_IMG" JDAD_GIT_SHA=canary "${COMPOSE[@]}" build >/dev/null
docker create --name "$TAG_ID-canary-ctr" "$CANARY_IMG:canary" >/dev/null
if docker export "$TAG_ID-canary-ctr" | tar -t | grep -E '(^|/)\.env$|(^|/)canary\.key$'; then
  echo "FAIL canary secret files were baked into the image" >&2
  exit 1
fi
docker rm "$TAG_ID-canary-ctr" >/dev/null
docker image rm -f "$CANARY_IMG:canary" >/dev/null
rm -f "$CANARY_ENV" "$CANARY_KEY"
echo "ok dockerignore canary (.env and *.key not in image)"

# --- literal quoted token is treated as unset (docker run --env)
"${COMPOSE[@]}" build >/dev/null
if docker run --rm --name "$TAG_ID-token-quote" \
  -e JDAD_TOKEN='""' \
  -e JDAD_ALLOWED_HOSTS=jdad-mcp.jondevs.com \
  "$IMG:$SHA" >/dev/null 2>"$WORKDIR/quote.err"; then
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

owner="$(docker run --rm --user 0 --entrypoint stat "$IMG:$SHA" -c '%u' /app/.venv)"
if [[ "$owner" != 0 ]]; then
  echo "FAIL /app/.venv owner is uid $owner, expected 0" >&2
  exit 1
fi
echo "ok /app/.venv is root-owned"

app_mode="$(docker run --rm --user 0 --entrypoint stat "$IMG:$SHA" -c '%a' /app)"
if [ "$app_mode" != "755" ]; then
  echo "FAIL /app mode is $app_mode, expected 755 so the compose uid can exec jdad-mcp" >&2
  exit 1
fi
if ! docker run --rm --user "$(id -u):$(id -g)" --entrypoint /bin/sh "$IMG:$SHA" -c 'command -v jdad-mcp >/dev/null'; then
  echo "FAIL compose uid cannot execute jdad-mcp (is /app mode 0700?)" >&2
  exit 1
fi
echo "ok /app is traversable and the compose uid can exec jdad-mcp"

# --- self-signed Origin cert, then the README install (isolated project)
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -days 1 -nodes \
  -keyout "$TESTHOME/.config/jdad/tls/origin.key" \
  -out "$TESTHOME/.config/jdad/tls/origin.crt" \
  -subj "/CN=jdad-mcp.jondevs.com" \
  -addext "subjectAltName=DNS:jdad-mcp.jondevs.com" >/dev/null 2>&1
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
token="$(tr -d '[:space:]' < "$TESTHOME/.config/jdad/token")"
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

# --- the token is a mounted file, not in the container environment
cid="$("${COMPOSE[@]}" ps -q jdad)"
if ! docker inspect -f '{{json .Config.Env}}' "$cid" | TOKEN="$token" python3 -c '
import json, os, sys
env = json.load(sys.stdin)
token = os.environ["TOKEN"]
if any(token in item for item in env):
    sys.exit("FAIL the token value is in the container environment (docker inspect)")
if "JDAD_TOKEN_FILE=/run/secrets/jdad_token" not in env:
    sys.exit("FAIL JDAD_TOKEN_FILE is not set to the mounted secret")
if any(item.startswith("JDAD_TOKEN=") for item in env):
    sys.exit("FAIL JDAD_TOKEN is still set in the container environment")
'; then
  exit 1
fi
if docker inspect "$cid" | grep -qF "$token"; then
  echo "FAIL the token value appears somewhere in docker inspect output" >&2
  exit 1
fi
echo "ok docker inspect shows JDAD_TOKEN_FILE, not the token"
limits="$(docker inspect -f '{{.HostConfig.Memory}} {{.HostConfig.PidsLimit}} {{.HostConfig.NanoCpus}} {{.HostConfig.LogConfig.Type}} {{index .HostConfig.LogConfig.Config "max-size"}} {{index .HostConfig.LogConfig.Config "max-file"}}' "$cid")"
if [[ "$limits" != "536870912 256 1000000000 json-file 10m 3" ]]; then
  echo "FAIL running container limits are '$limits'" >&2
  exit 1
fi
echo "ok the running container has the memory, pids, cpu and log limits"

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
# Always commit (even with no changes), so GOOD differs from SHA and the
# running $IMG:$SHA is a distinct "previous" image for the prune check.
git -C "$CLONE" -c user.name=jdad-test -c user.email=jdad-test@example.invalid \
  commit -q --allow-empty -m "test: working tree"
GOOD="$(git -C "$CLONE" rev-parse HEAD)"
if [[ "$GOOD" == "$SHA" ]]; then
  echo "FAIL the clone's good commit should differ from $SHA" >&2
  exit 1
fi

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
# previous is a distinct image (the one that was running before), not the current one.
prev_id="$(docker image inspect -f '{{.Id}}' "$IMG:previous")"
if [[ "$prev_id" != "$(docker image inspect -f '{{.Id}}' "$IMG:$SHA")" || "$prev_id" == "$(docker image inspect -f '{{.Id}}' "$IMG:$GOOD")" ]]; then
  echo "FAIL $IMG:previous should be the pre-update image $IMG:$SHA, distinct from $IMG:$GOOD" >&2
  exit 1
fi
echo "ok update-docker.sh pruned old sha tags and kept current + a distinct previous"

# --- prechecks refuse before touching the running service
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -days 1 -nodes \
  -keyout "$WORKDIR/other.key" -out "$WORKDIR/other.crt" -subj "/CN=other" >/dev/null 2>&1
chmod 600 "$WORKDIR/other.key"
if JDAD_SSL_KEYFILE_HOST="$WORKDIR/other.key" run_update > "$WORKDIR/mismatch.log" 2>&1; then
  echo "FAIL update-docker.sh accepted a key that does not match the cert" >&2
  exit 1
fi
grep -q "does not match the public key" "$WORKDIR/mismatch.log" || { cat "$WORKDIR/mismatch.log" >&2; echo "FAIL no mismatch message" >&2; exit 1; }
if [[ "$(running_image)" != "$IMG:$GOOD" ]]; then
  echo "FAIL a refused cert/key precheck changed the running image" >&2
  exit 1
fi
echo "ok precheck refuses a cert/key pair that does not match and leaves the service alone"

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

# expect_refusal LABEL PATTERN: run_update must fail with PATTERN and leave
# the running image alone.
expect_refusal() {
  local label="$1" pattern="$2"
  if run_update > "$WORKDIR/refuse.log" 2>&1; then
    echo "FAIL update-docker.sh accepted $label" >&2
    exit 1
  fi
  grep -q "$pattern" "$WORKDIR/refuse.log" || { cat "$WORKDIR/refuse.log" >&2; echo "FAIL no '$pattern' message for $label" >&2; exit 1; }
  if [[ "$(running_image)" != "$IMG:$GOOD" ]]; then
    echo "FAIL a refused precheck ($label) changed the running image" >&2
    exit 1
  fi
  echo "ok precheck refuses $label and leaves the service alone"
}
CONF="$TESTHOME/.config/jdad"

printf 'JDAD_TOKEN=old-style\n' >> "$CONF/jdad.env"
expect_refusal "an env file that still sets JDAD_TOKEN" "migrate-token.sh"
printf 'JDAD_ALLOWED_HOSTS=jdad-mcp.jondevs.com\n' > "$CONF/jdad.env"

chmod 440 "$CONF/token"
expect_refusal "a group-readable token file" "readable by group or others"
chmod 400 "$CONF/token"

mv "$CONF/token" "$CONF/token.hold"
expect_refusal "a missing token file" "token file .* is missing"
mv "$CONF/token.hold" "$CONF/token"

chmod 640 "$CONF/tls/origin.key"
expect_refusal "a group-readable origin key" "readable by group or others"
chmod 600 "$CONF/tls/origin.key"

# --- the health probe verifies the certificate: a name the certificate
# doesn't cover fails the update (and the rollback, which uses the same
# certificate) instead of passing with curl -k.
if JDAD_HEALTH_HOST=not-covered.example run_update > "$WORKDIR/certname.log" 2>&1; then
  echo "FAIL update-docker.sh passed a health check for a name the certificate doesn't cover" >&2
  cat "$WORKDIR/certname.log" >&2
  exit 1
fi
grep -qi "subject name\|does not match\|certificate" "$WORKDIR/certname.log" \
  || { cat "$WORKDIR/certname.log" >&2; echo "FAIL no certificate error in the update log" >&2; exit 1; }
echo "ok the health probe verifies the origin certificate for the public name (no -k)"
# That failure recorded the SHA; once the cause is fixed, a retry needs the
# explicit override, and a successful deploy clears the record.
if run_update > "$WORKDIR/recover.log" 2>&1; then
  echo "FAIL a recorded failed SHA was redeployed without JDAD_RETRY_FAILED=1" >&2
  exit 1
fi
grep -q "failed its health check on an earlier run" "$WORKDIR/recover.log" \
  || { cat "$WORKDIR/recover.log" >&2; echo "FAIL no 'earlier run' refusal" >&2; exit 1; }
if ! JDAD_RETRY_FAILED=1 run_update > "$WORKDIR/recover.log" 2>&1; then
  echo "FAIL update-docker.sh did not recover with JDAD_RETRY_FAILED=1 and the right health host" >&2
  cat "$WORKDIR/recover.log" >&2
  exit 1
fi
if [[ -e "$TESTHOME/.config/jdad/failed-sha" ]]; then
  echo "FAIL a successful deploy left the failed-sha record" >&2
  exit 1
fi
echo "ok a recorded failed SHA needs JDAD_RETRY_FAILED=1, and success clears the record"

# --- a commit that breaks only the KB fails the build (jdad-mcp --check)
# and never replaces the running container.
printf '# Bad\n\xff\xfe\n' > "$CLONE/practices/broken.md"
git -C "$CLONE" add practices/broken.md
git -C "$CLONE" -c user.name=jdad-test -c user.email=jdad-test@example.invalid \
  commit -q -m "test: KB file that is not UTF-8"
if run_update > "$WORKDIR/kbbreak.log" 2>&1; then
  echo "FAIL update-docker.sh deployed a commit whose KB doesn't load" >&2
  cat "$WORKDIR/kbbreak.log" >&2
  exit 1
fi
grep -q "practices/broken.md: not valid UTF-8" "$WORKDIR/kbbreak.log" \
  || { cat "$WORKDIR/kbbreak.log" >&2; echo "FAIL jdad-mcp --check did not name the broken file" >&2; exit 1; }
grep -q "the running container was not touched" "$WORKDIR/kbbreak.log" \
  || { cat "$WORKDIR/kbbreak.log" >&2; echo "FAIL no 'not touched' message" >&2; exit 1; }
if [[ "$(running_image)" != "$IMG:$GOOD" ]]; then
  echo "FAIL a KB-only break changed the running image to $(running_image)" >&2
  exit 1
fi
git -C "$CLONE" reset -q --hard "$GOOD"
echo "ok a commit that breaks only the KB fails the build and leaves the running container alone"

# --- real rollback: a commit that builds (and passes --check) but whose
# HTTP server can't start, probed through the real health URL (no override)
cat >> "$CLONE/src/jdad/server.py" <<'PY'


def create_http_app(token=None):  # noqa: F811 - deliberately broken for the rollback test
    raise SystemExit("deliberately broken HTTP app for the rollback test")
PY
git -C "$CLONE" -c user.name=jdad-test -c user.email=jdad-test@example.invalid \
  commit -q -am "test: deliberately broken"
BROKEN="$(git -C "$CLONE" rev-parse HEAD)"

if run_update > "$WORKDIR/rollback.log" 2>&1; then
  echo "FAIL update-docker.sh reported success for a broken commit" >&2
  cat "$WORKDIR/rollback.log" >&2
  exit 1
fi
if ! grep -q "rolled back to $IMG:$GOOD and https://jdad-mcp.jondevs.com:[0-9]*/healthz (via 127.0.0.1) is ok" "$WORKDIR/rollback.log"; then
  echo "FAIL rollback did not report a healthy rollback to $IMG:$GOOD" >&2
  cat "$WORKDIR/rollback.log" >&2
  exit 1
fi
if grep -q 'jondevs\.com:/healthz' "$WORKDIR/rollback.log"; then
  echo "FAIL update-docker.sh built a health URL with no port (would probe 443)" >&2
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

if [[ "$(git -C "$CLONE" rev-parse HEAD)" != "$GOOD" ]]; then
  echo "FAIL after rollback the checkout is at $(git -C "$CLONE" rev-parse HEAD), expected $GOOD" >&2
  exit 1
fi
if [[ "$(head -n1 "$TESTHOME/.config/jdad/failed-sha" 2>/dev/null)" != "$BROKEN" ]]; then
  echo "FAIL the failed SHA was not recorded" >&2
  exit 1
fi
echo "ok after rollback the checkout is back on $GOOD and $BROKEN is recorded as failed"

# The next run must not rebuild the same broken commit.
git -C "$CLONE" reset -q --hard "$BROKEN"
if run_update > "$WORKDIR/again.log" 2>&1; then
  echo "FAIL update-docker.sh redeployed a commit that already failed" >&2
  exit 1
fi
grep -q "failed its health check on an earlier run" "$WORKDIR/again.log" \
  || { cat "$WORKDIR/again.log" >&2; echo "FAIL no 'earlier run' refusal" >&2; exit 1; }
if [[ "$(running_image)" != "$IMG:$GOOD" ]]; then
  echo "FAIL the refusal changed the running image" >&2
  exit 1
fi
echo "ok a SHA that failed before is refused on the next run"
