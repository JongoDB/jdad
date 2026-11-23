#!/usr/bin/env bash
# Allow inbound TCP 443 to the JDAD origin only from Cloudflare's published
# IP ranges, over IPv4 and IPv6. Every other port, SSH included, is untouched.
#
# Docker-published ports bypass ufw and the INPUT chain: the packet is DNATed
# in PREROUTING and filtered in FORWARD, where Docker jumps to DOCKER-USER
# first. So the rules live in a dedicated JDAD-CF chain, hooked from:
#
#   DOCKER-USER  -p tcp -m conntrack --ctorigdstport 443 --ctdir ORIGINAL -j JDAD-CF
#                (after DNAT the port is 8443; conntrack still knows it was 443)
#   INPUT        -p tcp --dport 443 -j JDAD-CF
#                (the docker-proxy path, e.g. IPv6 when Docker's ip6tables is off)
#
# JDAD-CF returns (lets Docker's own rules decide) for loopback, docker0 and
# br-* (container traffic, including outbound HTTPS from builds), and for each
# Cloudflare range; everything else is dropped.
#
# The chain is replaced in one iptables-restore --noflush transaction, so a
# re-run never leaves it empty (open) or drop-only (Cloudflare locked out).
#
# Usage (as root on the droplet, except --dry-run):
#   firewall-cloudflare.sh install           copy to /usr/local/sbin/jdad-firewall, fetch and
#                                            cache ranges, install and enable the boot unit, apply
#   firewall-cloudflare.sh apply [--cached]  apply (fetches ranges unless --cached or --ranges-dir)
#   firewall-cloudflare.sh refresh           fetch ranges, show the diff against the cache, apply
#   firewall-cloudflare.sh rollback          remove the hooks and chains, disable the boot unit
#   firewall-cloudflare.sh status            show hooks, chains and cached ranges
#
# Options:
#   --dry-run          print what would run; change nothing; no root needed
#   --ranges-dir DIR   read DIR/ips-v4 and DIR/ips-v6 instead of fetching (offline, tests)
#   --cached           read the cached ranges in $JDAD_FW_STATE (used by the boot unit)
#
# Environment: JDAD_FW_STATE (default /etc/jdad/cloudflare), JDAD_FW_PORT (default 443).
set -euo pipefail

CHAIN="JDAD-CF"
PORT="${JDAD_FW_PORT:-443}"
STATE_DIR="${JDAD_FW_STATE:-/etc/jdad/cloudflare}"
INSTALL_PATH="/usr/local/sbin/jdad-firewall"
UNIT_NAME="jdad-firewall.service"
UNIT_PATH="/etc/systemd/system/$UNIT_NAME"
CF_V4_URL="https://www.cloudflare.com/ips-v4"
CF_V6_URL="https://www.cloudflare.com/ips-v6"
# Sanity floors: Cloudflare publishes about 15 IPv4 and 7 IPv6 ranges.
MIN_V4=5
MIN_V6=3

DRY_RUN=0
SOURCE="fetch"
RANGES_DIR=""
TMP=""

die() {
  echo "jdad-firewall: $*" >&2
  exit 1
}

cleanup() {
  if [[ -n "$TMP" && -d "$TMP" ]]; then
    rm -rf "$TMP"
  fi
}
trap cleanup EXIT

usage() {
  sed -n '2,/^set -euo pipefail/p' "$0" | sed -e '$d' -e 's/^# \{0,1\}//'
}

# Print a command in dry-run mode, run it otherwise.
run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '+ %s\n' "$*"
  else
    "$@"
  fi
}

require_root() {
  if [[ "$DRY_RUN" -eq 0 && "$(id -u)" -ne 0 ]]; then
    die "run as root (sudo $0 ...), or pass --dry-run"
  fi
}

require_tools() {
  local tool
  for tool in iptables ip6tables iptables-restore ip6tables-restore; do
    command -v "$tool" >/dev/null 2>&1 || die "$tool not found"
  done
}

# Validate one ranges file. Prints the cleaned list (one CIDR per line).
# family: 4 or 6.
validate_ranges() {
  local family="$1" file="$2" line count=0 prefix min_prefix floor
  [[ -s "$file" ]] || die "IPv$family range list $file is empty or missing"
  if [[ "$family" == 4 ]]; then
    min_prefix=8
    floor="$MIN_V4"
  else
    min_prefix=16
    floor="$MIN_V6"
  fi
  local -a out=()
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" ]] && continue
    if [[ "$family" == 4 ]]; then
      [[ "$line" =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})/([0-9]{1,2})$ ]] \
        || die "IPv4 range list has an invalid entry: '$line'"
      local octet
      for octet in "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" "${BASH_REMATCH[4]}"; do
        (( 10#$octet <= 255 )) || die "IPv4 range list has an invalid entry: '$line'"
      done
      prefix=$((10#${BASH_REMATCH[5]}))
      (( prefix <= 32 )) || die "IPv4 range list has an invalid prefix: '$line'"
    else
      [[ "$line" =~ ^[0-9a-fA-F:]+/([0-9]{1,3})$ && "$line" == *:* ]] \
        || die "IPv6 range list has an invalid entry: '$line'"
      prefix=$((10#${BASH_REMATCH[1]}))
      (( prefix <= 128 )) || die "IPv6 range list has an invalid prefix: '$line'"
    fi
    (( prefix >= min_prefix )) \
      || die "IPv$family range '$line' is broader than /$min_prefix; refusing (is the list poisoned?)"
    out+=("$line")
    count=$((count + 1))
  done < "$file"
  (( count >= floor )) \
    || die "IPv$family range list has $count entries, fewer than $floor; refusing (fetch failed or list truncated?)"
  printf '%s\n' "${out[@]}" | sort -u
}

fetch_ranges() {
  local dest="$1"
  command -v curl >/dev/null 2>&1 || die "curl not found; cannot fetch Cloudflare ranges"
  curl -fsS --proto '=https' --tlsv1.2 --max-time 20 -o "$dest/ips-v4.raw" "$CF_V4_URL" \
    || die "could not fetch $CF_V4_URL"
  curl -fsS --proto '=https' --tlsv1.2 --max-time 20 -o "$dest/ips-v6.raw" "$CF_V6_URL" \
    || die "could not fetch $CF_V6_URL"
}

# Load and validate ranges into $TMP/ips-v4 and $TMP/ips-v6.
load_ranges() {
  TMP="$(mktemp -d)"
  case "$SOURCE" in
    fetch)
      fetch_ranges "$TMP"
      ;;
    cached)
      [[ -f "$STATE_DIR/ips-v4" && -f "$STATE_DIR/ips-v6" ]] \
        || die "no cached ranges in $STATE_DIR; run 'install' or 'refresh' first"
      cp "$STATE_DIR/ips-v4" "$TMP/ips-v4.raw"
      cp "$STATE_DIR/ips-v6" "$TMP/ips-v6.raw"
      ;;
    dir)
      cp "$RANGES_DIR/ips-v4" "$TMP/ips-v4.raw" 2>/dev/null || die "$RANGES_DIR/ips-v4 not found"
      cp "$RANGES_DIR/ips-v6" "$TMP/ips-v6.raw" 2>/dev/null || die "$RANGES_DIR/ips-v6 not found"
      ;;
  esac
  validate_ranges 4 "$TMP/ips-v4.raw" > "$TMP/ips-v4"
  validate_ranges 6 "$TMP/ips-v6.raw" > "$TMP/ips-v6"
}

# The iptables-restore payload that (re)defines the JDAD-CF chain.
# Declaring a user chain under --noflush flushes that chain only.
chain_payload() {
  local ranges="$1" cidr
  echo "*filter"
  echo ":$CHAIN - [0:0]"
  echo "-A $CHAIN -i lo -j RETURN"
  echo "-A $CHAIN -i docker0 -j RETURN"
  echo "-A $CHAIN -i br-+ -j RETURN"
  while IFS= read -r cidr; do
    echo "-A $CHAIN -s $cidr -j RETURN"
  done < "$ranges"
  echo "-A $CHAIN -j DROP"
  echo "COMMIT"
}

# Set after JDAD_FW_PORT is validated (plain arrays: macOS /bin/bash 3.2 has no mapfile).
DOCKER_HOOK=()
INPUT_HOOK=()
set_hooks() {
  DOCKER_HOOK=(-p tcp -m conntrack --ctorigdstport "$PORT" --ctdir ORIGINAL -j "$CHAIN")
  INPUT_HOOK=(-p tcp --dport "$PORT" -j "$CHAIN")
}

chain_exists() {
  "$1" -w -S "$2" >/dev/null 2>&1
}

apply_family() {
  local family="$1" ipt restore ranges
  if [[ "$family" == 4 ]]; then
    ipt=iptables
    restore=iptables-restore
  else
    ipt=ip6tables
    restore=ip6tables-restore
  fi
  ranges="$TMP/ips-v$family"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "# IPv$family: $restore --noflush <<EOF"
    chain_payload "$ranges"
    echo "# EOF"
    echo "+ $ipt -w -C DOCKER-USER ${DOCKER_HOOK[*]} || $ipt -w -I DOCKER-USER 1 ${DOCKER_HOOK[*]}"
    echo "+ $ipt -w -C INPUT ${INPUT_HOOK[*]} || $ipt -w -I INPUT 1 ${INPUT_HOOK[*]}"
    return
  fi

  chain_exists "$ipt" DOCKER-USER \
    || die "$ipt has no DOCKER-USER chain. Is Docker running? For IPv6, Docker's ip6tables support must be on (default since Docker 27); see 'docker info' and /etc/docker/daemon.json. Nothing was changed for IPv$family."
  chain_payload "$ranges" | "$restore" -w --noflush
  "$ipt" -w -C DOCKER-USER "${DOCKER_HOOK[@]}" 2>/dev/null \
    || "$ipt" -w -I DOCKER-USER 1 "${DOCKER_HOOK[@]}"
  "$ipt" -w -C INPUT "${INPUT_HOOK[@]}" 2>/dev/null \
    || "$ipt" -w -I INPUT 1 "${INPUT_HOOK[@]}"
  echo "jdad-firewall: IPv$family: $CHAIN has $(wc -l < "$ranges" | tr -d ' ') Cloudflare ranges; DOCKER-USER and INPUT hooked for tcp/$PORT"
}

cache_ranges() {
  run install -d -m 0755 "$STATE_DIR"
  run install -m 0644 "$TMP/ips-v4" "$STATE_DIR/ips-v4"
  run install -m 0644 "$TMP/ips-v6" "$STATE_DIR/ips-v6"
}

cmd_apply() {
  require_root
  [[ "$DRY_RUN" -eq 1 ]] || require_tools
  load_ranges
  # Check both families before changing either, so a missing IPv6 chain
  # can't leave IPv4 locked down and IPv6 open without a loud failure.
  if [[ "$DRY_RUN" -eq 0 ]]; then
    chain_exists iptables DOCKER-USER || die "iptables has no DOCKER-USER chain (is Docker running?). Nothing was changed."
    chain_exists ip6tables DOCKER-USER || die "ip6tables has no DOCKER-USER chain. Docker's IPv6 filtering must be on (default since Docker 27; check 'ip6tables' in /etc/docker/daemon.json). Nothing was changed."
  fi
  apply_family 4
  apply_family 6
  if [[ "$SOURCE" != "cached" ]]; then
    cache_ranges
  fi
}

cmd_refresh() {
  require_root
  # refresh always re-reads the source of truth: the network, or --ranges-dir in tests.
  if [[ "$SOURCE" == "cached" ]]; then SOURCE="fetch"; fi
  [[ "$DRY_RUN" -eq 1 ]] || require_tools
  load_ranges
  local family changed=0
  for family in 4 6; do
    if [[ -f "$STATE_DIR/ips-v$family" ]]; then
      if ! diff -u "$STATE_DIR/ips-v$family" "$TMP/ips-v$family" >/dev/null; then
        echo "jdad-firewall: IPv$family ranges changed:"
        diff -u "$STATE_DIR/ips-v$family" "$TMP/ips-v$family" | tail -n +3 || true
        changed=1
      fi
    else
      echo "jdad-firewall: no cached IPv$family ranges yet"
      changed=1
    fi
  done
  if [[ "$changed" -eq 0 ]]; then
    echo "jdad-firewall: ranges unchanged"
  fi
  if [[ "$DRY_RUN" -eq 0 ]]; then
    chain_exists iptables DOCKER-USER || die "iptables has no DOCKER-USER chain. Nothing was changed."
    chain_exists ip6tables DOCKER-USER || die "ip6tables has no DOCKER-USER chain. Nothing was changed."
  fi
  apply_family 4
  apply_family 6
  cache_ranges
}

unit_text() {
  cat <<EOF
[Unit]
Description=JDAD: allow TCP $PORT to the origin only from Cloudflare (DOCKER-USER)
Documentation=https://github.com/JongoDB/jdad/blob/main/deploy/firewall-cloudflare.sh
After=docker.service
Requires=docker.service
PartOf=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=$INSTALL_PATH apply --cached

[Install]
WantedBy=docker.service
EOF
}

cmd_install() {
  require_root
  [[ "$DRY_RUN" -eq 1 ]] || require_tools
  run install -o root -g root -m 0755 "$0" "$INSTALL_PATH"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "# $UNIT_PATH:"
    unit_text
  else
    unit_text > "$UNIT_PATH.tmp"
    chmod 0644 "$UNIT_PATH.tmp"
    mv "$UNIT_PATH.tmp" "$UNIT_PATH"
  fi
  cmd_apply
  run systemctl daemon-reload
  run systemctl enable "$UNIT_NAME"
  # Starting the unit re-applies from the cache just written; idempotent.
  run systemctl start "$UNIT_NAME"
}

remove_family() {
  local family="$1" ipt
  if [[ "$family" == 4 ]]; then ipt=iptables; else ipt=ip6tables; fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "+ while $ipt -w -C DOCKER-USER ${DOCKER_HOOK[*]}; do $ipt -w -D DOCKER-USER ${DOCKER_HOOK[*]}; done"
    echo "+ while $ipt -w -C INPUT ${INPUT_HOOK[*]}; do $ipt -w -D INPUT ${INPUT_HOOK[*]}; done"
    echo "+ $ipt -w -F $CHAIN && $ipt -w -X $CHAIN"
    return
  fi
  while "$ipt" -w -C DOCKER-USER "${DOCKER_HOOK[@]}" 2>/dev/null; do
    "$ipt" -w -D DOCKER-USER "${DOCKER_HOOK[@]}"
  done
  while "$ipt" -w -C INPUT "${INPUT_HOOK[@]}" 2>/dev/null; do
    "$ipt" -w -D INPUT "${INPUT_HOOK[@]}"
  done
  if chain_exists "$ipt" "$CHAIN"; then
    "$ipt" -w -F "$CHAIN"
    "$ipt" -w -X "$CHAIN"
  fi
  echo "jdad-firewall: IPv$family: removed $CHAIN and its hooks"
}

cmd_rollback() {
  require_root
  if [[ "$DRY_RUN" -eq 0 ]] && command -v systemctl >/dev/null 2>&1 && [[ -f "$UNIT_PATH" ]]; then
    systemctl disable "$UNIT_NAME" >/dev/null 2>&1 || true
    systemctl stop "$UNIT_NAME" >/dev/null 2>&1 || true
  elif [[ "$DRY_RUN" -eq 1 ]]; then
    echo "+ systemctl disable $UNIT_NAME; systemctl stop $UNIT_NAME"
  fi
  remove_family 4
  remove_family 6
  echo "jdad-firewall: TCP $PORT is open to all sources again. Left in place if present: $UNIT_PATH (disabled), $INSTALL_PATH, the cache in $STATE_DIR."
}

cmd_status() {
  local ipt
  for ipt in iptables ip6tables; do
    echo "== $ipt DOCKER-USER"
    "$ipt" -w -S DOCKER-USER 2>&1 || true
    echo "== $ipt INPUT (jdad rules)"
    "$ipt" -w -S INPUT 2>&1 | grep -- "$CHAIN" || echo "(no $CHAIN hook)"
    echo "== $ipt $CHAIN"
    "$ipt" -w -S "$CHAIN" 2>&1 || true
  done
  echo "== cached ranges in $STATE_DIR"
  wc -l "$STATE_DIR/ips-v4" "$STATE_DIR/ips-v6" 2>&1 || true
  if command -v systemctl >/dev/null 2>&1; then
    echo "== $UNIT_NAME"
    systemctl is-enabled "$UNIT_NAME" 2>&1 || true
  fi
}

main() {
  local cmd="${1:-}"
  [[ -n "$cmd" ]] || { usage; exit 2; }
  shift
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) DRY_RUN=1 ;;
      --cached) SOURCE="cached" ;;
      --ranges-dir)
        [[ $# -ge 2 ]] || die "--ranges-dir needs a directory"
        SOURCE="dir"
        RANGES_DIR="$2"
        shift
        ;;
      -h|--help) usage; exit 0 ;;
      *) die "unknown option: $1" ;;
    esac
    shift
  done
  [[ "$PORT" =~ ^[0-9]+$ ]] || die "JDAD_FW_PORT must be a port number"
  set_hooks
  case "$cmd" in
    install) cmd_install ;;
    apply) cmd_apply ;;
    refresh) cmd_refresh ;;
    rollback) cmd_rollback ;;
    status) cmd_status ;;
    -h|--help|help) usage ;;
    *) usage; exit 2 ;;
  esac
}

main "$@"
