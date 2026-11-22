#!/usr/bin/env bash
# deploy/migrate-token.sh: moves JDAD_TOKEN from the env file to a 0400
# token file without printing it, keeps the other env lines, is idempotent,
# and refuses to pick between two different tokens.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/deploy/migrate-token.sh"
# shellcheck source=../deploy/common.sh
source "$ROOT/deploy/common.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail() {
  echo "FAIL $*" >&2
  exit 1
}

setup() {
  rm -rf "$TMP/home"
  mkdir -p "$TMP/home/.config/jdad"
  export JDAD_ENV_FILE="$TMP/home/.config/jdad/jdad.env"
  export JDAD_TOKEN_FILE_HOST="$TMP/home/.config/jdad/token"
}

SECRET="migrate-test-value-$RANDOM$RANDOM"

# --- a quoted token moves; other lines stay; nothing prints the value
setup
printf 'JDAD_ALLOWED_HOSTS=jdad-mcp.jondevs.com\nJDAD_TOKEN="%s"\nOTHER=1\n' "$SECRET" > "$JDAD_ENV_FILE"
chmod 600 "$JDAD_ENV_FILE"
out="$(bash "$SCRIPT" 2>&1)"
[[ "$out" != *"$SECRET"* ]] || fail "the script printed the token"
[[ "$(head -n1 "$JDAD_TOKEN_FILE_HOST")" == "$SECRET" ]] || fail "token file content is wrong"
[[ "$(file_mode "$JDAD_TOKEN_FILE_HOST")" == 400 ]] || fail "token file mode is $(file_mode "$JDAD_TOKEN_FILE_HOST"), expected 400"
if grep -q JDAD_TOKEN "$JDAD_ENV_FILE"; then fail "JDAD_TOKEN is still in the env file"; fi
grep -qx 'JDAD_ALLOWED_HOSTS=jdad-mcp.jondevs.com' "$JDAD_ENV_FILE" || fail "lost JDAD_ALLOWED_HOSTS"
grep -qx 'OTHER=1' "$JDAD_ENV_FILE" || fail "lost an unrelated line"
[[ "$(file_mode "$JDAD_ENV_FILE")" == 600 ]] || fail "env file mode is $(file_mode "$JDAD_ENV_FILE"), expected 600"
echo "ok migrate-token moves a quoted token to a 0400 file, keeps other lines, prints nothing secret"

# --- re-run is a no-op
out="$(bash "$SCRIPT" 2>&1)"
[[ "$out" == *"already migrated"* ]] || fail "re-run should say already migrated: $out"
echo "ok migrate-token is idempotent"

# --- the server reads what the script wrote (same normalisation)
got="$(cd "$ROOT" && JDAD_TOKEN_FILE="$JDAD_TOKEN_FILE_HOST" uv run --frozen python -c \
  'from jdad.server import resolve_token; import hashlib; print(hashlib.sha256(resolve_token().encode()).hexdigest())')"
want="$(printf '%s' "$SECRET" | openssl dgst -sha256 -r | cut -d' ' -f1)"
[[ "$got" == "$want" ]] || fail "the server reads a different token from the file"
echo "ok the server reads the migrated token file"

# --- same token already in a file: the env line is removed
setup
printf 'JDAD_TOKEN=%s\n' "$SECRET" > "$JDAD_ENV_FILE"
(umask 077 && printf '%s\n' "$SECRET" > "$JDAD_TOKEN_FILE_HOST")
bash "$SCRIPT" >/dev/null
if grep -q JDAD_TOKEN "$JDAD_ENV_FILE"; then fail "env line kept although the file already held the same token"; fi
echo "ok migrate-token finishes a half-done migration"

# --- different tokens: refuse, change nothing
setup
printf 'JDAD_TOKEN=%s\n' "$SECRET" > "$JDAD_ENV_FILE"
(umask 077 && printf 'some-other-token\n' > "$JDAD_TOKEN_FILE_HOST")
before_env="$(cat "$JDAD_ENV_FILE")"
rc=0
out="$(bash "$SCRIPT" 2>&1)" || rc=$?
[[ "$rc" -ne 0 ]] || fail "accepted two different tokens"
[[ "$out" == *"different token"* ]] || fail "unexpected message: $out"
[[ "$out" != *"$SECRET"* && "$out" != *"some-other-token"* ]] || fail "printed a token while refusing"
[[ "$(cat "$JDAD_ENV_FILE")" == "$before_env" ]] || fail "env file changed on refusal"
echo "ok migrate-token refuses two different tokens and changes nothing"

# --- nothing to migrate and no file: clear error
setup
printf 'JDAD_ALLOWED_HOSTS=x\n' > "$JDAD_ENV_FILE"
rc=0
out="$(bash "$SCRIPT" 2>&1)" || rc=$?
[[ "$rc" -ne 0 && "$out" == *"openssl rand"* ]] || fail "missing token should explain how to create one: $out"
echo "ok migrate-token explains how to create a token when there is none"
