#!/usr/bin/env bash
# Idempotent update for the JDAD Docker deploy on the droplet.
# Prechecks the token file, the env file, the Origin cert/key pair and the
# container uid, git pull --ff-only, rebuild and restart the compose
# service (project name "jdad"), then require a local HTTPS /healthz of 200
# that verifies the origin certificate (no -k) for the public hostname.
# Rolls back to the previous image tag if the health check fails, and
# prunes old jdad:<sha> images (keeping the current and previous ones)
# after a healthy update. Fails loudly on any step.
#
# Tests override JDAD_COMPOSE_PROJECT, JDAD_IMAGE_REPO and JDAD_PUBLISH
# so they never touch the production project, port or images.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$HERE/common.sh"

ENV_FILE="${JDAD_ENV_FILE:-$HOME/.config/jdad/jdad.env}"
TOKEN_FILE="${JDAD_TOKEN_FILE_HOST:-$HOME/.config/jdad/token}"
# The name the origin certificate must be valid for; the health probe
# connects to 127.0.0.1 but verifies the certificate for this name.
HEALTH_HOST="${JDAD_HEALTH_HOST:-jdad-mcp.jondevs.com}"
TLS_DIR="${JDAD_TLS_DIR:-$HOME/.config/jdad/tls}"
CERT_FILE="${JDAD_SSL_CERTFILE_HOST:-$TLS_DIR/origin.crt}"
KEY_FILE="${JDAD_SSL_KEYFILE_HOST:-$TLS_DIR/origin.key}"
PROJECT="${JDAD_COMPOSE_PROJECT:-jdad}"
COMPOSE=(docker compose -p "$PROJECT" -f "$HERE/docker-compose.yml")
IMAGE_REPO="${JDAD_IMAGE_REPO:-jdad}"
export JDAD_IMAGE_REPO="$IMAGE_REPO"
export JDAD_TOKEN_FILE_HOST="$TOKEN_FILE"

# Check for a checkout before any git command, so a plain copy gets one
# clear error instead of git's "fatal: not a git repository" first.
if ! is_git_checkout "$ROOT"; then
  echo "jdad: no git checkout at $ROOT" >&2
  exit 1
fi

export JDAD_GIT_SHA="${JDAD_GIT_SHA:-$(git -C "$ROOT" rev-parse HEAD)}"
export JDAD_UID="${JDAD_UID:-$(id -u)}"
export JDAD_GID="${JDAD_GID:-$(id -g)}"

if ! command -v docker >/dev/null 2>&1; then
  echo "jdad: docker not found on PATH" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "jdad: docker daemon is not available (is this user in the docker group?)" >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "jdad: curl not found; cannot probe /healthz" >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "jdad: openssl not found; cannot check the origin certificate and key" >&2
  exit 1
fi

# The host port that maps to 8443 (443 in prod, an ephemeral port in
# tests): ask compose, falling back to JDAD_PUBLISH or 443. Returns 1 with
# no output when no port is known (for example a restart-looping container
# on an ephemeral port), so callers fail closed instead of probing some
# other service on 443.
health_port() {
  local mapped port=""
  mapped="$("${COMPOSE[@]}" port jdad 8443 2>/dev/null | head -n1 || true)"
  if [[ -n "$mapped" ]]; then
    port="${mapped##*:}"
  elif [[ -z "${JDAD_PUBLISH:-}" ]]; then
    port=443
  elif [[ "${JDAD_PUBLISH##*:}" =~ ^[0-9]+$ ]]; then
    port="${JDAD_PUBLISH##*:}"
  fi
  if [[ -z "$port" ]]; then
    return 1
  fi
  printf '%s\n' "$port"
}

# The URL for /healthz, for messages and for the JDAD_HEALTH_URL override.
health_url() {
  if [[ -n "${JDAD_HEALTH_URL:-}" ]]; then
    printf '%s\n' "$JDAD_HEALTH_URL"
    return
  fi
  local port
  port="$(health_port)" || return 1
  printf 'https://%s:%s/healthz (via 127.0.0.1)\n' "$HEALTH_HOST" "$port"
}

precheck_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "jdad: env file $ENV_FILE is missing (mode 0600; holds JDAD_ALLOWED_HOSTS, not the token)" >&2
    return 1
  fi
  if [[ -n "$(parse_jdad_token "$ENV_FILE")" ]]; then
    echo "jdad: $ENV_FILE still sets JDAD_TOKEN. The token now lives in $TOKEN_FILE so it isn't visible in 'docker inspect'. Run ./deploy/migrate-token.sh, then re-run this script." >&2
    return 1
  fi
  if [[ ! -f "$TOKEN_FILE" || -L "$TOKEN_FILE" ]]; then
    echo "jdad: token file $TOKEN_FILE is missing or a symlink (see ./deploy/migrate-token.sh, or the README to create one)" >&2
    return 1
  fi
  if [[ "$(file_owner_uid "$TOKEN_FILE")" != "$JDAD_UID" ]]; then
    echo "jdad: token file $TOKEN_FILE must be owned by uid $JDAD_UID, the uid the container runs as" >&2
    return 1
  fi
  if ! mode_is_private "$TOKEN_FILE"; then
    echo "jdad: token file $TOKEN_FILE is readable by group or others (mode $(file_mode "$TOKEN_FILE")); chmod 400" >&2
    return 1
  fi
  if [[ -z "$(tr -d '[:space:]\"'"'"'' < "$TOKEN_FILE")" ]]; then
    echo "jdad: token file $TOKEN_FILE is empty; refusing to update" >&2
    return 1
  fi
  if [[ ! -f "$CERT_FILE" ]]; then
    echo "jdad: origin certificate $CERT_FILE is missing" >&2
    return 1
  fi
  if [[ ! -f "$KEY_FILE" ]]; then
    echo "jdad: origin private key $KEY_FILE is missing" >&2
    return 1
  fi
  if ! openssl x509 -in "$CERT_FILE" -noout 2>/dev/null; then
    echo "jdad: $CERT_FILE is not a readable PEM certificate" >&2
    return 1
  fi
  if ! openssl x509 -in "$CERT_FILE" -noout -checkend 0 >/dev/null 2>&1; then
    echo "jdad: $CERT_FILE has expired" >&2
    return 1
  fi
  local cert_pub key_pub
  cert_pub="$(openssl x509 -in "$CERT_FILE" -noout -pubkey 2>/dev/null)"
  if ! key_pub="$(openssl pkey -in "$KEY_FILE" -pubout 2>/dev/null)"; then
    echo "jdad: $KEY_FILE is not a readable private key" >&2
    return 1
  fi
  if [[ -z "$cert_pub" || "$cert_pub" != "$key_pub" ]]; then
    echo "jdad: $KEY_FILE does not match the public key in $CERT_FILE; refusing to update" >&2
    return 1
  fi
  if ! mode_is_private "$KEY_FILE"; then
    echo "jdad: $KEY_FILE is readable by group or others (mode $(file_mode "$KEY_FILE")); chmod 400 or 600 so only the container uid can read it" >&2
    return 1
  fi
}

precheck_uid() {
  if [[ "$JDAD_UID" == 0 ]]; then
    echo "jdad: refusing to run the container as root (JDAD_UID=0). Run this script as a non-root deploy user in the docker group (see the README)." >&2
    return 1
  fi
}

probe_health() {
  local body port
  local -a target
  if [[ -n "${JDAD_HEALTH_URL:-}" ]]; then
    target=("$JDAD_HEALTH_URL")
  elif port="$(health_port)"; then
    # Connect to 127.0.0.1 but send SNI and Host for the public name, and
    # trust only the origin certificate on disk (curl accepts a leaf as the
    # anchor). A wrong, expired or mismatched certificate fails here and the
    # update rolls back. No -k.
    target=(--resolve "$HEALTH_HOST:$port:127.0.0.1" "https://$HEALTH_HOST:$port/healthz")
  else
    return 1  # no published port yet: unhealthy, nothing probed
  fi
  if body="$(curl -fsS --max-time 5 --cacert "$CERT_FILE" "${target[@]}" 2>"$HEALTH_ERR")"; then
    if [[ "$body" == '{"status":"ok"}' ]]; then
      return 0
    fi
    echo "jdad: $(health_url) returned unexpected body: $body" >&2
    return 1
  fi
  return 1
}

wait_for_health() {
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18; do
    if probe_health; then
      return 0
    fi
    sleep 1
  done
  echo "jdad: $(health_url || echo '/healthz (no published port)') did not return 200 {\"status\":\"ok\"} after waiting" >&2
  if [[ -s "$HEALTH_ERR" ]]; then
    echo "jdad: last curl error: $(head -n 1 "$HEALTH_ERR")" >&2
  fi
  return 1
}

current_image_ref() {
  local cid
  cid="$("${COMPOSE[@]}" ps -q jdad 2>/dev/null || true)"
  if [[ -n "$cid" ]]; then
    docker inspect -f '{{.Config.Image}}' "$cid" 2>/dev/null || true
  fi
}

rollback() {
  local prev="$1"
  if [[ -z "$prev" ]]; then
    echo "jdad: no previous image to roll back to" >&2
    return 1
  fi
  local prev_sha="${prev#"${IMAGE_REPO}":}"
  if ! docker image inspect "$prev" >/dev/null 2>&1; then
    echo "jdad: previous image $prev is not present; cannot roll back" >&2
    return 1
  fi
  echo "jdad: health check failed; rolling back to $prev" >&2
  JDAD_GIT_SHA="$prev_sha" "${COMPOSE[@]}" up -d --no-build --force-recreate
  if ! wait_for_health; then
    echo "jdad: rollback to $prev also failed health check" >&2
    return 1
  fi
  echo "jdad: rolled back to $prev and $(health_url) is ok" >&2
  return 0
}

# Remove ${IMAGE_REPO}:<40-hex sha> tags except the ones to keep.
prune_images() {
  local tag ref
  local -a keep=("$@")
  while IFS= read -r tag; do
    [[ "$tag" =~ ^[0-9a-f]{40}$ ]] || continue
    ref="${IMAGE_REPO}:${tag}"
    if printf '%s\n' "${keep[@]}" | grep -qxF "$ref"; then
      continue
    fi
    if docker image rm "$ref" >/dev/null 2>&1; then
      echo "jdad: pruned old image $ref"
    else
      echo "jdad: could not prune $ref (still in use?); leaving it" >&2
    fi
  done < <(docker image ls "$IMAGE_REPO" --format '{{.Tag}}')
}

HEALTH_ERR="$(mktemp)"
trap 'rm -f "$HEALTH_ERR"' EXIT

precheck_uid
precheck_env

before="$(git -C "$ROOT" rev-parse HEAD)"
previous_image="$(current_image_ref || true)"
if [[ -n "$previous_image" ]]; then
  docker tag "$previous_image" "${IMAGE_REPO}:previous" 2>/dev/null || true
fi

if [[ "${JDAD_SKIP_GIT_PULL:-}" == 1 ]]; then
  echo "jdad: skipping git pull (JDAD_SKIP_GIT_PULL=1)"
else
  git -C "$ROOT" pull --ff-only
fi
after="$(git -C "$ROOT" rev-parse HEAD)"
export JDAD_GIT_SHA="$after"

"${COMPOSE[@]}" up -d --build

if ! wait_for_health; then
  rollback_target="$previous_image"
  if [[ -z "$rollback_target" ]] && docker image inspect "${IMAGE_REPO}:previous" >/dev/null 2>&1; then
    rollback_target="${IMAGE_REPO}:previous"
  fi
  rollback "$rollback_target" || true
  exit 1
fi

prune_images "${IMAGE_REPO}:${after}" "$previous_image"

if [[ "$before" != "$after" ]]; then
  echo "jdad: updated $before -> $after and $(health_url) is ok"
else
  echo "jdad: already up to date at $after and $(health_url) is ok"
fi
