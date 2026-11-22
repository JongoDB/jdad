#!/usr/bin/env bash
# Idempotent update for a JDAD checkout on the LXC host.
# git pull --ff-only (as the jdad user), sync deps and restart only when
# HEAD changes, and start the service if it is not already running.
set -euo pipefail

cd "$(dirname "$0")"
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"

UV="$(resolve_uv)"

if [[ ! -d "$JDAD_ROOT/.git" ]]; then
  echo "jdad: no git checkout at $JDAD_ROOT" >&2
  exit 1
fi

before="$(run_as_jdad git -C "$JDAD_ROOT" rev-parse HEAD)"
run_as_jdad git -C "$JDAD_ROOT" fetch --prune
run_as_jdad git -C "$JDAD_ROOT" pull --ff-only
after="$(run_as_jdad git -C "$JDAD_ROOT" rev-parse HEAD)"

sync_deps() {
  run_as_jdad env UV_PYTHON_PREFERENCE=only-system "$UV" --directory "$JDAD_ROOT" sync --frozen --no-dev
}

service_active() {
  systemctl is-active --quiet "$JDAD_SERVICE"
}

if ! service_active; then
  sync_deps
  systemctl start "$JDAD_SERVICE"
  echo "jdad: started $JDAD_SERVICE at $after"
elif [[ "$before" != "$after" ]]; then
  sync_deps
  systemctl restart "$JDAD_SERVICE"
  echo "jdad: updated $before -> $after and restarted $JDAD_SERVICE"
else
  echo "jdad: already up to date at $after"
fi

systemctl is-active --quiet "$JDAD_SERVICE"
