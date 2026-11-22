#!/usr/bin/env bash
# is_git_checkout (deploy/common.sh) must accept a normal clone and a git
# worktree (.git is a file there), and reject plain dirs and subdirs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=../deploy/common.sh
source "$ROOT/deploy/common.sh"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git init -q "$TMP/repo"
git -C "$TMP/repo" -c user.name=t -c user.email=t@example.invalid commit -q --allow-empty -m init
git -C "$TMP/repo" worktree add -q "$TMP/wt" -b wt-test
mkdir -p "$TMP/plain" "$TMP/repo/sub"

check() {
  local want="$1" dir="$2"
  if is_git_checkout "$dir"; then got=yes; else got=no; fi
  if [[ "$got" != "$want" ]]; then
    echo "FAIL is_git_checkout $dir: got $got, want $want" >&2
    exit 1
  fi
}

check yes "$TMP/repo"
check yes "$TMP/wt"
[[ -f "$TMP/wt/.git" ]] || { echo "FAIL worktree fixture has no .git file" >&2; exit 1; }
check no "$TMP/plain"
check no "$TMP/repo/sub"
check no "$TMP/missing"
echo "ok is_git_checkout accepts a clone and a worktree, rejects plain dirs and subdirs"
