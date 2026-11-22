#!/usr/bin/env bash
# Idempotent update for the JDAD Docker deploy on the droplet.
# Prechecks the env file and Origin cert, git pull --ff-only, rebuild
# and restart the compose service (project name "jdad"), then require
# a local HTTPS /healthz of 200. Rolls back to the previous image tag
# if the health check fails. Fails loudly on any step.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$HERE/common.sh"

ENV_FILE="${JDAD_ENV_FILE:-$HOME/.config/jdad/jdad.env}"
TLS_DIR="${JDAD_TLS_DIR:-$HOME/.config/jdad/tls}"
CERT_FILE="${JDAD_SSL_CERTFILE_HOST:-$TLS_DIR/origin.crt}"
KEY_FILE="${JDAD_SSL_KEYFILE_HOST:-$TLS_DIR/origin.key}"
COMPOSE=(docker compose -f "$HERE/docker-compose.yml")
HEALTH_URL="${JDAD_HEALTH_URL:-https://127.0.0.1/healthz}"
IMAGE_REPO="jdad"

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
if [[ ! -d "$ROOT/.git" ]]; then
  echo "jdad: no git checkout at $ROOT" >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "jdad: curl not found; cannot probe $HEALTH_URL" >&2
  exit 1
fi

precheck_env() {
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "jdad: env file $ENV_FILE is missing (mode 0600; must set a non-empty JDAD_TOKEN)" >&2
    return 1
  fi
  local token
  token="$(parse_jdad_token "$ENV_FILE")"
  if [[ -z "$token" ]]; then
    echo "jdad: JDAD_TOKEN in $ENV_FILE is empty or quoted-empty; refusing to update" >&2
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
  local mode others
  mode="$(stat -c '%a' "$KEY_FILE")"
  others=$((10#${mode: -1}))
  if (( others != 0 )); then
    echo "jdad: $KEY_FILE is world-accessible (mode $mode); chmod 400 or 600 so only the container uid can read it" >&2
    return 1
  fi
}

probe_health() {
  local body
  # -k: the Origin CA (or a local self-signed cert) is not in the public
  # trust store, and this probe hits 127.0.0.1 rather than the hostname.
  if body="$(curl -fsSk --max-time 5 "$HEALTH_URL")"; then
    if [[ "$body" == '{"status":"ok"}' ]]; then
      return 0
    fi
    echo "jdad: $HEALTH_URL returned unexpected body: $body" >&2
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
  echo "jdad: $HEALTH_URL did not return 200 {\"status\":\"ok\"} after waiting" >&2
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
  echo "jdad: rolled back to $prev and $HEALTH_URL is ok" >&2
  return 0
}

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

if [[ "$before" != "$after" ]]; then
  echo "jdad: updated $before -> $after and $HEALTH_URL is ok"
else
  echo "jdad: already up to date at $after and $HEALTH_URL is ok"
fi
