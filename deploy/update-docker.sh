#!/usr/bin/env bash
# Idempotent update for the JDAD Docker deploy on the droplet.
# git pull --ff-only, rebuild and restart the compose service, then
# require a local /healthz of 200. Fails loudly on any step.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

ENV_FILE="${JDAD_ENV_FILE:-$HOME/.config/jdad/jdad.env}"
COMPOSE=(docker compose -f "$HERE/docker-compose.yml" --project-directory "$ROOT")
HEALTH_URL="${JDAD_HEALTH_URL:-http://127.0.0.1/healthz}"

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
if [[ ! -f "$ENV_FILE" ]]; then
  echo "jdad: env file $ENV_FILE is missing (mode 0600; must set a non-empty JDAD_TOKEN)" >&2
  exit 1
fi

before="$(git -C "$ROOT" rev-parse HEAD)"
git -C "$ROOT" pull --ff-only
after="$(git -C "$ROOT" rev-parse HEAD)"

"${COMPOSE[@]}" up -d --build

if ! command -v curl >/dev/null 2>&1; then
  echo "jdad: curl not found; cannot probe $HEALTH_URL" >&2
  exit 1
fi

ok=0
for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
  if body="$(curl -fsS --max-time 5 "$HEALTH_URL")"; then
    if [[ "$body" == '{"status":"ok"}' ]]; then
      ok=1
      break
    fi
    echo "jdad: $HEALTH_URL returned unexpected body: $body" >&2
    exit 1
  fi
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  echo "jdad: $HEALTH_URL did not return 200 {\"status\":\"ok\"} after waiting" >&2
  exit 1
fi

if [[ "$before" != "$after" ]]; then
  echo "jdad: updated $before -> $after and $HEALTH_URL is ok"
else
  echo "jdad: already up to date at $after and $HEALTH_URL is ok"
fi
