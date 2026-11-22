#!/usr/bin/env bash
# Idempotent first-time (and repair) install of JDAD on the LXC host.
# Creates the jdad system user, clones /opt/jdad as that user, writes
# /etc/jdad.env at mode 0600 with a token placeholder only, and installs
# and enables the systemd unit.
set -euo pipefail

cd "$(dirname "$0")"
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"

require_root

UV="$(resolve_uv)"

if ! getent passwd "$JDAD_USER" >/dev/null; then
  useradd --system --user-group --home-dir "$JDAD_ROOT" --shell /usr/sbin/nologin \
    --comment "JDAD MCP server" "$JDAD_USER"
  echo "jdad: created system user $JDAD_USER"
else
  echo "jdad: user $JDAD_USER already exists"
fi

install -d -o "$JDAD_USER" -g "$JDAD_USER" -m 0755 "$JDAD_ROOT"

if [[ ! -d "$JDAD_ROOT/.git" ]]; then
  if [[ -n "$(ls -A "$JDAD_ROOT" 2>/dev/null || true)" ]]; then
    echo "jdad: $JDAD_ROOT exists and is not an empty git checkout; refusing to clone into it" >&2
    exit 1
  fi
  run_as_jdad git clone "$JDAD_REPO" "$JDAD_ROOT"
  echo "jdad: cloned $JDAD_REPO into $JDAD_ROOT"
else
  echo "jdad: checkout already present at $JDAD_ROOT"
fi

chown -R "$JDAD_USER:$JDAD_USER" "$JDAD_ROOT"

run_as_jdad env UV_PYTHON_PREFERENCE=only-system "$UV" --directory "$JDAD_ROOT" sync --frozen --no-dev
# Ensure the venv lives under the checkout, not under /root or /home.
if [[ ! -x "$JDAD_ROOT/.venv/bin/jdad-mcp" ]]; then
  echo "jdad: expected $JDAD_ROOT/.venv/bin/jdad-mcp after uv sync" >&2
  exit 1
fi

if [[ ! -f "$JDAD_ENV" ]]; then
  install -o root -g root -m 0600 "$JDAD_ROOT/deploy/jdad.env.example" "$JDAD_ENV"
  echo "jdad: wrote $JDAD_ENV (mode 0600) with the JDAD_TOKEN placeholder only"
else
  echo "jdad: leaving existing $JDAD_ENV in place"
fi

install -o root -g root -m 0644 "$JDAD_ROOT/deploy/jdad.service" "/etc/systemd/system/$JDAD_SERVICE"
systemctl daemon-reload
systemctl enable "$JDAD_SERVICE"

token=""
# shellcheck disable=SC1090
token="$(awk -F= '/^JDAD_TOKEN=/{print $2; exit}' "$JDAD_ENV" 2>/dev/null || true)"
if [[ -n "${token}" ]]; then
  systemctl restart "$JDAD_SERVICE"
  echo "jdad: enabled and started $JDAD_SERVICE"
else
  echo "jdad: enabled $JDAD_SERVICE but did not start it; set JDAD_TOKEN in $JDAD_ENV (mode 0600), then: systemctl start $JDAD_SERVICE"
fi
