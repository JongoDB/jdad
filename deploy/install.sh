#!/usr/bin/env bash
# Idempotent first-time (and repair) install of JDAD on the LXC host.
# Creates the jdad system user (home /var/lib/jdad), clones /opt/jdad as
# that user, writes /etc/jdad.env at mode 0600 with a token placeholder
# only, and installs and enables the systemd unit.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
source "$HERE/common.sh"

require_root

UV="$(resolve_uv)"

if ! getent passwd "$JDAD_USER" >/dev/null; then
  useradd --system --user-group --home-dir "$JDAD_HOME" --shell /usr/sbin/nologin \
    --comment "JDAD MCP server" "$JDAD_USER"
  echo "jdad: created system user $JDAD_USER (home $JDAD_HOME)"
else
  current_home="$(getent passwd "$JDAD_USER" | cut -d: -f6)"
  if [[ "$current_home" != "$JDAD_HOME" ]]; then
    usermod -d "$JDAD_HOME" "$JDAD_USER"
    echo "jdad: moved $JDAD_USER home from $current_home to $JDAD_HOME"
  else
    echo "jdad: user $JDAD_USER already exists"
  fi
fi

# Home is outside the checkout so a deploy key in $JDAD_HOME/.ssh does not
# make /opt/jdad non-empty, and so the uv cache is not in the KB tree.
install -d -o "$JDAD_USER" -g "$JDAD_USER" -m 0755 "$JDAD_HOME"
install -d -o "$JDAD_USER" -g "$JDAD_USER" -m 0700 "$JDAD_HOME/.ssh"
if [[ ! -f "$JDAD_HOME/.ssh/config" && -f "$HERE/ssh-config.example" ]]; then
  install -o "$JDAD_USER" -g "$JDAD_USER" -m 0600 "$HERE/ssh-config.example" "$JDAD_HOME/.ssh/config"
  echo "jdad: wrote $JDAD_HOME/.ssh/config (mode 0600); add the deploy key at $JDAD_HOME/.ssh/id_ed25519 (mode 0600)"
fi

install -d -o "$JDAD_USER" -g "$JDAD_USER" -m 0755 "$JDAD_ROOT"

if [[ ! -d "$JDAD_ROOT/.git" ]]; then
  if [[ -n "$(ls -A "$JDAD_ROOT" 2>/dev/null || true)" ]]; then
    echo "jdad: $JDAD_ROOT exists and is not an empty git checkout; refusing to clone into it" >&2
    exit 1
  fi
  if ! run_as_jdad git clone "$JDAD_REPO" "$JDAD_ROOT"; then
    echo "jdad: git clone failed. For github.com over SSH, install a deploy key at $JDAD_HOME/.ssh/id_ed25519 (mode 0600) owned by $JDAD_USER, with $JDAD_HOME/.ssh mode 0700 and the ssh config Host github.com entry. sudo -u $JDAD_USER has no SSH agent. Then re-run this script." >&2
    exit 1
  fi
  echo "jdad: cloned $JDAD_REPO into $JDAD_ROOT"
else
  echo "jdad: checkout already present at $JDAD_ROOT"
fi

chown -R "$JDAD_USER:$JDAD_USER" "$JDAD_ROOT"

run_as_jdad env HOME="$JDAD_HOME" UV_PYTHON_PREFERENCE=only-system "$UV" --directory "$JDAD_ROOT" sync --frozen --no-dev
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

if [[ -n "$(parse_jdad_token "$JDAD_ENV")" ]]; then
  systemctl restart "$JDAD_SERVICE"
  echo "jdad: enabled and started $JDAD_SERVICE"
else
  echo "jdad: enabled $JDAD_SERVICE but did not start it; set a non-empty JDAD_TOKEN in $JDAD_ENV (mode 0600), then: systemctl start $JDAD_SERVICE"
fi
