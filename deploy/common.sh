#!/usr/bin/env bash
# Shared helpers for deploy/install.sh and deploy/update.sh.
# Sourced, not executed.

JDAD_USER="${JDAD_USER:-jdad}"
JDAD_ROOT="${JDAD_ROOT:-/opt/jdad}"
JDAD_SERVICE="${JDAD_SERVICE:-jdad.service}"
JDAD_ENV="${JDAD_ENV:-/etc/jdad.env}"
JDAD_REPO="${JDAD_REPO:-git@github.com:JongoDB/jdad.git}"

jdad_home() {
  local home
  home="$(getent passwd "$JDAD_USER" 2>/dev/null | cut -d: -f6 || true)"
  printf '%s\n' "${home:-$JDAD_ROOT}"
}

# uv must be executable, and not live under /root or another user's home
# (ProtectHome=true; sudo -u jdad cannot run /root/.local/bin/uv).
_uv_ok() {
  local path="$1" home
  [[ -n "$path" && -x "$path" ]] || return 1
  home="$(jdad_home)"
  case "$path" in
    "$home"/*|/usr/*|/opt/*|/bin/*)
      return 0
      ;;
    /root/*|/home/*)
      return 1
      ;;
  esac
  return 0
}

# Prefer an explicit UV=, then PATH, then well-known absolute paths
# (sudo's secure_path often omits ~/.local/bin).
resolve_uv() {
  local candidate home
  if [[ -n "${UV:-}" ]]; then
    if _uv_ok "$UV"; then
      printf '%s\n' "$UV"
      return 0
    fi
    echo "jdad: UV=$UV is not usable by $JDAD_USER (need an executable not under /root or another home)" >&2
    return 1
  fi
  if candidate="$(command -v uv 2>/dev/null)" && _uv_ok "$candidate"; then
    printf '%s\n' "$candidate"
    return 0
  fi
  home="$(jdad_home)"
  for candidate in /usr/local/bin/uv "$home/.local/bin/uv"; do
    if _uv_ok "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  echo "jdad: uv not found (tried PATH, /usr/local/bin/uv, $home/.local/bin/uv). Install uv system-wide (e.g. /usr/local/bin/uv) or set UV to an absolute path $JDAD_USER can execute." >&2
  return 1
}

run_as_jdad() {
  if [[ "$(id -un)" == "$JDAD_USER" ]]; then
    "$@"
  else
    sudo -u "$JDAD_USER" -- "$@"
  fi
}

require_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "jdad: run this script as root (e.g. sudo $0)" >&2
    exit 1
  fi
}
