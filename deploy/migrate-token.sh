#!/usr/bin/env bash
# One-time migration for the Docker deploy: move JDAD_TOKEN out of the env
# file (where `docker inspect` shows it) into a token file that compose
# mounts as a secret. Never prints the token. Idempotent.
#
#   ./deploy/migrate-token.sh      # as the deploy user, then ./deploy/update-docker.sh
#
# Env file:   ${JDAD_ENV_FILE:-~/.config/jdad/jdad.env}
# Token file: ${JDAD_TOKEN_FILE_HOST:-~/.config/jdad/token}  (written 0400)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$HERE/common.sh"

ENV_FILE="${JDAD_ENV_FILE:-$HOME/.config/jdad/jdad.env}"
TOKEN_FILE="${JDAD_TOKEN_FILE_HOST:-$HOME/.config/jdad/token}"

die() {
  echo "jdad: $*" >&2
  exit 1
}

# The token in the token file, normalised the way the server reads it.
file_token() {
  local raw first last
  raw="$(cat "$TOKEN_FILE")"
  raw="${raw//$'\r'/}"
  raw="${raw#"${raw%%[![:space:]]*}"}"
  raw="${raw%"${raw##*[![:space:]]}"}"
  if [[ ${#raw} -ge 2 ]]; then
    first="${raw:0:1}"
    last="${raw: -1}"
    if [[ "$first" == "$last" && ( "$first" == '"' || "$first" == "'" ) ]]; then
      raw="${raw:1:${#raw}-2}"
    fi
  fi
  printf '%s' "$raw"
}

[[ -f "$ENV_FILE" ]] || die "env file $ENV_FILE not found"
[[ ! -L "$TOKEN_FILE" ]] || die "$TOKEN_FILE is a symlink; refusing"

token="$(parse_jdad_token "$ENV_FILE")"

if [[ -z "$token" ]]; then
  if [[ -s "$TOKEN_FILE" ]]; then
    echo "jdad: already migrated: $ENV_FILE has no JDAD_TOKEN and $TOKEN_FILE exists"
    exit 0
  fi
  die "no JDAD_TOKEN in $ENV_FILE and no $TOKEN_FILE. Create a new token with: (umask 077; openssl rand -hex 32 > $TOKEN_FILE; chmod 400 $TOKEN_FILE)"
fi

if [[ -e "$TOKEN_FILE" ]]; then
  if [[ "$(file_token)" != "$token" ]]; then
    die "$TOKEN_FILE already exists with a different token than $ENV_FILE; refusing to choose. Decide which one is current, remove the other, and re-run."
  fi
else
  tmp="$(dirname "$TOKEN_FILE")/.token.$$.tmp"
  (umask 077 && printf '%s\n' "$token" > "$tmp")
  chmod 400 "$tmp"
  mv "$tmp" "$TOKEN_FILE"
fi

# Check the copy before touching the env file.
[[ "$(file_token)" == "$token" ]] || die "the token written to $TOKEN_FILE doesn't match; $ENV_FILE left unchanged"
chmod 400 "$TOKEN_FILE"
unset token

# Drop every JDAD_TOKEN line from the env file, keeping the rest and mode 0600.
tmp_env="$(dirname "$ENV_FILE")/.jdad.env.$$.tmp"
(umask 077 && grep -v -E '^[[:space:]]*JDAD_TOKEN=' "$ENV_FILE" > "$tmp_env" || true)
chmod 600 "$tmp_env"
mv "$tmp_env" "$ENV_FILE"

[[ -z "$(parse_jdad_token "$ENV_FILE")" ]] || die "JDAD_TOKEN is still in $ENV_FILE"
echo "jdad: moved JDAD_TOKEN from $ENV_FILE to $TOKEN_FILE (mode $(file_mode "$TOKEN_FILE")). Next: ./deploy/update-docker.sh"
