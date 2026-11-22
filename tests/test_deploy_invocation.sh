#!/usr/bin/env bash
# Prove the documented invocations can source common.sh, and that
# parse_jdad_token treats empty / quoted-empty values as unset.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

expect_source_ok() {
  local label="$1" rc out
  shift
  set +e
  out="$("$@" 2>&1)"
  rc=$?
  set -e
  if [[ "$out" == *"common.sh: No such file"* || "$out" == *"common.sh: No such file or directory"* ]]; then
    echo "FAIL $label: scripts did not find common.sh" >&2
    printf '%s\n' "$out" >&2
    exit 1
  fi
  if [[ "$out" != *"run this script as root"* && "$out" != *"no git checkout"* && "$out" != *"uv not found"* ]]; then
    # Non-root is the usual case here: install.sh should reach require_root.
    # update.sh may reach uv or the checkout check if sourced correctly.
    echo "FAIL $label: unexpected output (rc=$rc):" >&2
    printf '%s\n' "$out" >&2
    exit 1
  fi
  echo "ok $label (rc=$rc)"
}

expect_source_ok "relative install from repo root" ./deploy/install.sh
expect_source_ok "relative update from repo root" ./deploy/update.sh
expect_source_ok "absolute install" "$ROOT/deploy/install.sh"
expect_source_ok "absolute update" "$ROOT/deploy/update.sh"

# shellcheck source=../deploy/common.sh
source "$ROOT/deploy/common.sh"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

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
