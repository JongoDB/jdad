#!/usr/bin/env bash
# Idempotent update for a JDAD checkout on the LXC host.
# git pull --ff-only, sync deps and restart only when HEAD changes,
# and start the service if it is not already running.
set -euo pipefail

ROOT="${JDAD_ROOT:-/opt/jdad}"
SERVICE="${JDAD_SERVICE:-jdad.service}"

if ! command -v uv >/dev/null 2>&1; then
  echo "jdad: uv is not on PATH; install uv before running update.sh" >&2
  exit 1
fi

if [[ ! -d "$ROOT/.git" ]]; then
  echo "jdad: no git checkout at $ROOT" >&2
  exit 1
fi

cd "$ROOT"
before="$(git rev-parse HEAD)"
git fetch --prune
git pull --ff-only
after="$(git rev-parse HEAD)"

sync_deps() {
  uv sync --frozen --no-dev
}

service_active() {
  systemctl is-active --quiet "$SERVICE"
}

if ! service_active; then
  sync_deps
  systemctl start "$SERVICE"
  echo "jdad: started $SERVICE at $after"
elif [[ "$before" != "$after" ]]; then
  sync_deps
  systemctl restart "$SERVICE"
  echo "jdad: updated $before -> $after and restarted $SERVICE"
else
  echo "jdad: already up to date at $after"
fi

systemctl is-active --quiet "$SERVICE"
