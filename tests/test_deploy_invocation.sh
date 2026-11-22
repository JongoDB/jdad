#!/usr/bin/env bash
# Prove the documented invocations can source common.sh, and that
# parse_jdad_token treats empty / quoted-empty values as unset.
#
# When this script is run as root (EUID 0), it must not execute the real
# install.sh or update.sh against the host. It drops to an unprivileged
# user so those scripts stop at require_root after sourcing. If it cannot
# drop privileges, it skips the invocation checks with a clear message.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# update.sh has no require_root and would act on $JDAD_ROOT (default
# /opt/jdad) if that checkout is writable. Point it at an empty temp dir
# so a privilege-dropped run cannot mutate a real tree.
EMPTY_ROOT="$(mktemp -d)"
trap 'rm -rf "$EMPTY_ROOT"' EXIT
export JDAD_ROOT="$EMPTY_ROOT"

# Run a command, dropping privileges first when we are root.
invoke() {
  if [[ "$(id -u)" -ne 0 ]]; then
    "$@"
    return
  fi
  local uid gid
  uid="$(getent passwd nobody | cut -d: -f3)"
  gid="$(getent passwd nobody | cut -d: -f4)"
  if [[ -z "$uid" || -z "$gid" ]]; then
    return 125
  fi
  if command -v setpriv >/dev/null 2>&1 && setpriv --reuid="$uid" --regid="$gid" --clear-groups -- true 2>/dev/null; then
    setpriv --reuid="$uid" --regid="$gid" --clear-groups -- "$@"
    return
  fi
  if command -v runuser >/dev/null 2>&1 && runuser -u nobody -- true 2>/dev/null; then
    runuser -u nobody -- "$@"
    return
  fi
  return 125
}

expect_source_ok() {
  local label="$1" rc out
  shift
  set +e
  out="$(invoke "$@" 2>&1)"
  rc=$?
  set -e
  if [[ "$rc" -eq 125 && "$(id -u)" -eq 0 ]]; then
    echo "skip deploy invocation checks: running as root (EUID 0) and cannot drop privileges to sandbox them; refusing to run install.sh/update.sh against this host"
    return 2
  fi
  if [[ "$out" == *"common.sh: No such file"* || "$out" == *"common.sh: No such file or directory"* ]]; then
    echo "FAIL $label: scripts did not find common.sh" >&2
    printf '%s\n' "$out" >&2
    exit 1
  fi
  if [[ "$out" != *"run this script as root"* && "$out" != *"no git checkout"* && "$out" != *"uv not found"* ]]; then
    # After a privilege drop (or when already unprivileged), install.sh should
    # reach require_root. update.sh may reach uv or the checkout check.
    echo "FAIL $label: unexpected output (rc=$rc):" >&2
    printf '%s\n' "$out" >&2
    exit 1
  fi
  echo "ok $label (rc=$rc)"
}

if [[ "$(id -u)" -eq 0 ]]; then
  echo "running as root; dropping to nobody so install.sh/update.sh cannot mutate this host"
fi

run_invocation() {
  local rc=0
  expect_source_ok "$@" || rc=$?
  if [[ "$rc" -eq 2 ]]; then
    return 2
  fi
  if [[ "$rc" -ne 0 ]]; then
    exit "$rc"
  fi
  return 0
}

invocations_ok=1
run_invocation "relative install from repo root" ./deploy/install.sh || invocations_ok=0
if [[ "$invocations_ok" -eq 1 ]]; then
  run_invocation "relative update from repo root" ./deploy/update.sh
  run_invocation "absolute install" "$ROOT/deploy/install.sh"
  run_invocation "absolute update" "$ROOT/deploy/update.sh"
  run_invocation "bootstrap-user from repo root" ./deploy/install.sh --bootstrap-user
fi

# shellcheck source=../deploy/common.sh
source "$ROOT/deploy/common.sh"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$EMPTY_ROOT" "$tmpdir"' EXIT

printf 'JDAD_TOKEN=\n' >"$tmpdir/empty"
printf 'JDAD_TOKEN=""\n' >"$tmpdir/quoted"
printf "JDAD_TOKEN=''\n" >"$tmpdir/squoted"
printf 'JDAD_TOKEN=   \n' >"$tmpdir/spaces"
printf 'JDAD_TOKEN="secret-value"\n' >"$tmpdir/set"
printf 'OTHER=1\n' >"$tmpdir/missing"

[[ -z "$(parse_jdad_token "$tmpdir/empty")" ]] || { echo "FAIL empty token"; exit 1; }
[[ -z "$(parse_jdad_token "$tmpdir/quoted")" ]] || { echo "FAIL quoted empty token"; exit 1; }
[[ -z "$(parse_jdad_token "$tmpdir/squoted")" ]] || { echo "FAIL single-quoted empty token"; exit 1; }
[[ -z "$(parse_jdad_token "$tmpdir/spaces")" ]] || { echo "FAIL whitespace token"; exit 1; }
[[ -z "$(parse_jdad_token "$tmpdir/missing")" ]] || { echo "FAIL missing token"; exit 1; }
[[ "$(parse_jdad_token "$tmpdir/set")" == "secret-value" ]] || { echo "FAIL set token"; exit 1; }
echo "ok parse_jdad_token"
