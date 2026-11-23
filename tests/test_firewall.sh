#!/usr/bin/env bash
# Tests for deploy/firewall-cloudflare.sh.
#
# 1. Offline, anywhere: --dry-run output for fixture ranges, and refusal of
#    bad range lists (empty, too short, too broad, malformed).
# 2. When Docker is available: a real apply, re-apply, range change, refusal
#    and rollback with iptables and ip6tables inside a throwaway container
#    (default caps plus NET_ADMIN, unique name per run). DOCKER-USER is created by hand
#    there, the way Docker creates it on the droplet. Nothing touches this
#    host's firewall.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/deploy/firewall-cloudflare.sh"
FIX="$ROOT/tests/fixtures/cloudflare"
TMP="$(mktemp -d)"
CTR="jdad-fwtest-$$-$RANDOM"
cleanup() {
  rm -rf "$TMP"
  if command -v docker >/dev/null 2>&1; then
    docker rm -f "$CTR" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

fail() {
  echo "FAIL $*" >&2
  exit 1
}

# ---- 1. dry run --------------------------------------------------------
out="$(bash "$SCRIPT" apply --dry-run --ranges-dir "$FIX")"
v4="$(printf '%s\n' "$out" | sed -n '/^# IPv4:/,/^# EOF/p')"
v6="$(printf '%s\n' "$out" | sed -n '/^# IPv6:/,/^# EOF/p')"
[[ -n "$v4" && -n "$v6" ]] || fail "dry run did not print both families:
$out"
for section in "$v4" "$v6"; do
  first_rules="$(printf '%s\n' "$section" | grep -- '^-A JDAD-CF' | head -3)"
  [[ "$first_rules" == "-A JDAD-CF -i lo -j RETURN
-A JDAD-CF -i docker0 -j RETURN
-A JDAD-CF -i br-+ -j RETURN" ]] || fail "container and loopback returns must come first:
$section"
  last_rule="$(printf '%s\n' "$section" | grep -- '^-A JDAD-CF' | tail -1)"
  [[ "$last_rule" == "-A JDAD-CF -j DROP" ]] || fail "DROP must be the last rule, got: $last_rule"
  printf '%s\n' "$section" | grep -qx ':JDAD-CF - \[0:0\]' || fail "chain is not declared (and so not flushed)"
done
[[ "$(printf '%s\n' "$v4" | grep -c -- '-s .* -j RETURN')" == 15 ]] || fail "expected 15 IPv4 ranges"
[[ "$(printf '%s\n' "$v6" | grep -c -- '-s .* -j RETURN')" == 7 ]] || fail "expected 7 IPv6 ranges"
printf '%s\n' "$v4" | grep -qx -- '-A JDAD-CF -s 173.245.48.0/20 -j RETURN' || fail "missing IPv4 range"
printf '%s\n' "$v6" | grep -qx -- '-A JDAD-CF -s 2606:4700::/32 -j RETURN' || fail "missing IPv6 range"
if printf '%s\n' "$v4" | grep -q ':.*/'; then fail "IPv6 range in the IPv4 payload"; fi
printf '%s\n' "$out" | grep -qF -- '-I DOCKER-USER 1 -p tcp -m conntrack --ctorigdstport 443 --ctdir ORIGINAL -j JDAD-CF' \
  || fail "DOCKER-USER hook must match the original port 443"
printf '%s\n' "$out" | grep -qF -- 'iptables -w -I INPUT 1 -p tcp --dport 443 -j JDAD-CF' || fail "missing IPv4 INPUT hook"
printf '%s\n' "$out" | grep -qF -- 'ip6tables -w -I INPUT 1 -p tcp --dport 443 -j JDAD-CF' || fail "missing IPv6 INPUT hook"
if printf '%s\n' "$out" | grep -qE -- '--dport (22|80)\b'; then fail "touches a port other than 443"; fi
echo "ok firewall dry run: both families, container returns first, ranges, DROP last, hooks on 443"

rb="$(bash "$SCRIPT" rollback --dry-run)"
printf '%s\n' "$rb" | grep -qF 'iptables -w -D DOCKER-USER' || fail "rollback dry run does not remove the hook"
printf '%s\n' "$rb" | grep -qF 'ip6tables -w -F JDAD-CF && ip6tables -w -X JDAD-CF' || fail "rollback dry run does not delete the IPv6 chain"
echo "ok firewall rollback dry run"

# ---- refusals ---------------------------------------------------------
expect_refusal() {
  local label="$1" v4file="$2" v6file="$3" pattern="$4" dir="$TMP/$1" rc=0 err
  mkdir -p "$dir"
  cp "$v4file" "$dir/ips-v4"
  cp "$v6file" "$dir/ips-v6"
  err="$(bash "$SCRIPT" apply --dry-run --ranges-dir "$dir" 2>&1 >/dev/null)" || rc=$?
  [[ "$rc" -ne 0 ]] || fail "$label: bad ranges were accepted"
  [[ "$err" == *"$pattern"* ]] || fail "$label: expected '$pattern' in: $err"
  echo "ok refuses $label"
}
: > "$TMP/empty"
printf '0.0.0.0/0\n' | cat - "$FIX/ips-v4" > "$TMP/v4-any"
printf '::/0\n' | cat - "$FIX/ips-v6" > "$TMP/v6-any"
printf '10.0.0.0/4\n' | cat - "$FIX/ips-v4" > "$TMP/v4-broad"
head -3 "$FIX/ips-v4" > "$TMP/v4-short"
printf '<html>error</html>\n' | cat - "$FIX/ips-v4" > "$TMP/v4-html"
printf '300.1.1.0/24\n' | cat - "$FIX/ips-v4" > "$TMP/v4-octet"
cat "$FIX/ips-v6" "$FIX/ips-v4" > "$TMP/v6-mixed"
expect_refusal "an empty IPv4 list" "$TMP/empty" "$FIX/ips-v6" "empty or missing"
expect_refusal "0.0.0.0/0" "$TMP/v4-any" "$FIX/ips-v6" "broader than /8"
expect_refusal "::/0" "$FIX/ips-v4" "$TMP/v6-any" "broader than /16"
expect_refusal "a /4 range" "$TMP/v4-broad" "$FIX/ips-v6" "broader than /8"
expect_refusal "a truncated list" "$TMP/v4-short" "$FIX/ips-v6" "fewer than 5"
expect_refusal "an HTML error page" "$TMP/v4-html" "$FIX/ips-v6" "invalid entry"
expect_refusal "an octet over 255" "$TMP/v4-octet" "$FIX/ips-v6" "invalid entry"
expect_refusal "IPv4 ranges in the IPv6 list" "$FIX/ips-v4" "$TMP/v6-mixed" "invalid entry"

rc=0
bash "$SCRIPT" bogus >/dev/null 2>&1 || rc=$?
[[ "$rc" -eq 2 ]] || fail "unknown subcommand should exit 2, got $rc"
rc=0
JDAD_FW_PORT='443; rm' bash "$SCRIPT" apply --dry-run --ranges-dir "$FIX" >/dev/null 2>&1 || rc=$?
[[ "$rc" -ne 0 ]] || fail "a non-numeric JDAD_FW_PORT was accepted"
echo "ok rejects an unknown subcommand and a non-numeric port"

# ---- 2. real iptables in a throwaway container ------------------------
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "skip firewall container test: docker is not available on this box"
  exit 0
fi

BASE="$(sed -n 's/^FROM \(python:3.12-slim@sha256:[0-9a-f]*\).*/\1/p' "$ROOT/Dockerfile" | head -1)"
[[ -n "$BASE" ]] || fail "could not read the pinned base image from the Dockerfile"

docker run -d --name "$CTR" --cap-add NET_ADMIN \
  --network bridge -v "$ROOT:/repo:ro" "$BASE" sleep 600 >/dev/null
if ! docker exec "$CTR" sh -c 'apt-get update -qq >/dev/null && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends iptables >/dev/null' >"$TMP/apt.log" 2>&1; then
  cat "$TMP/apt.log" >&2
  fail "could not install iptables in the test container (network?)"
fi

in_ctr() {
  docker exec -e JDAD_FW_STATE=/tmp/jdad-fw "$CTR" "$@"
}
fw() {
  in_ctr bash /repo/deploy/firewall-cloudflare.sh "$@"
}

# Without DOCKER-USER in ip6tables, nothing changes in either family.
in_ctr iptables -N DOCKER-USER
rc=0
fw apply --ranges-dir /repo/tests/fixtures/cloudflare >/dev/null 2>"$TMP/nov6.err" || rc=$?
[[ "$rc" -ne 0 ]] || fail "apply succeeded without an ip6tables DOCKER-USER chain"
grep -q "Nothing was changed" "$TMP/nov6.err" || fail "missing-chain error should say nothing changed: $(cat "$TMP/nov6.err")"
if in_ctr iptables -S JDAD-CF >/dev/null 2>&1; then fail "IPv4 chain was created although IPv6 was refused"; fi
echo "ok apply refuses, and changes nothing, when ip6tables has no DOCKER-USER chain"

in_ctr ip6tables -N DOCKER-USER
fw apply --ranges-dir /repo/tests/fixtures/cloudflare >/dev/null
snapshot() {
  local ipt
  for ipt in iptables ip6tables; do
    in_ctr "$ipt" -S DOCKER-USER
    in_ctr "$ipt" -S INPUT
    in_ctr "$ipt" -S JDAD-CF
  done
}
first="$(snapshot)"
for ipt in iptables ip6tables; do
  [[ "$(in_ctr "$ipt" -S DOCKER-USER | grep -c JDAD-CF)" == 1 ]] || fail "$ipt: expected one DOCKER-USER hook"
  [[ "$(in_ctr "$ipt" -S INPUT | grep -c JDAD-CF)" == 1 ]] || fail "$ipt: expected one INPUT hook"
  [[ "$(in_ctr "$ipt" -S JDAD-CF | tail -1)" == "-A JDAD-CF -j DROP" ]] || fail "$ipt: DROP is not last"
done
in_ctr iptables -S DOCKER-USER | grep -q -- '--ctorigdstport 443' || fail "DOCKER-USER hook lost the original-port match"
[[ "$(in_ctr iptables -S JDAD-CF | grep -c -- '-s ')" == 15 ]] || fail "IPv4 chain should hold 15 ranges"
[[ "$(in_ctr ip6tables -S JDAD-CF | grep -c -- '-s ')" == 7 ]] || fail "IPv6 chain should hold 7 ranges"
in_ctr test -s /tmp/jdad-fw/ips-v4 || fail "ranges were not cached"
echo "ok real apply: one hook per chain per family, 15 + 7 ranges, DROP last, ranges cached"

fw apply --ranges-dir /repo/tests/fixtures/cloudflare >/dev/null
[[ "$(snapshot)" == "$first" ]] || fail "re-apply changed the rules (not idempotent)"
fw apply --cached >/dev/null
[[ "$(snapshot)" == "$first" ]] || fail "apply --cached (the boot unit) differs from the first apply"
echo "ok re-apply and apply --cached are idempotent"

# A changed range list replaces the chain's contents; it doesn't append.
mkdir -p "$TMP/changed"
grep -v '^173\.245\.48\.0/20$' "$FIX/ips-v4" > "$TMP/changed/ips-v4"
printf '198.51.100.0/24\n' >> "$TMP/changed/ips-v4"
cp "$FIX/ips-v6" "$TMP/changed/ips-v6"
docker cp "$TMP/changed" "$CTR:/tmp/changed" >/dev/null
fw refresh --ranges-dir /tmp/changed > "$TMP/refresh.out"
grep -q '198.51.100.0/24' "$TMP/refresh.out" || fail "refresh did not show the range diff"
if in_ctr iptables -S JDAD-CF | grep -q '173.245.48.0/20'; then fail "a removed range is still allowed"; fi
in_ctr iptables -S JDAD-CF | grep -q '198.51.100.0/24' || fail "a new range was not added"
[[ "$(in_ctr iptables -S JDAD-CF | grep -c -- '-s ')" == 15 ]] || fail "refresh appended instead of replacing"
echo "ok refresh shows the diff and replaces the chain"

# Bad ranges are refused before anything changes.
before="$(snapshot)"
mkdir -p "$TMP/bad"
printf '0.0.0.0/0\n' > "$TMP/bad/ips-v4"
cp "$FIX/ips-v6" "$TMP/bad/ips-v6"
docker cp "$TMP/bad" "$CTR:/tmp/bad" >/dev/null
if fw apply --ranges-dir /tmp/bad >/dev/null 2>&1; then fail "applied a 0.0.0.0/0 list"; fi
[[ "$(snapshot)" == "$before" ]] || fail "a refused apply changed the live rules"
echo "ok a refused range list leaves the live rules untouched"

# Behaviour, not just rule text: a listener on 443 in the container, and a
# second container on the same bridge as the "internet". Its address isn't a
# Cloudflare range, so it must be dropped; loopback must still connect; once
# its address is in the list, it connects. (Exercises the INPUT hook; the
# DOCKER-USER hook needs a real published port, see the PR's Unverified list.)
CLIENT="$CTR-client"
in_ctr sh -c 'nohup python3 -m http.server 443 --bind 0.0.0.0 >/tmp/http.log 2>&1 &'
docker run -d --name "$CLIENT" --network bridge "$BASE" sleep 300 >/dev/null
trap 'cleanup; docker rm -f "$CLIENT" >/dev/null 2>&1 || true' EXIT
CTR_IP="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$CTR")"
CLIENT_IP="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$CLIENT")"
probe='import socket,sys
s=socket.socket(); s.settimeout(3)
try:
    s.connect((sys.argv[1], 443)); print("open")
except OSError as e:
    print("blocked", type(e).__name__)'
for _ in 1 2 3 4 5 6 7 8 9 10; do
  [[ "$(in_ctr python3 -c "$probe" 127.0.0.1)" == open ]] && break
  sleep 0.3
done
[[ "$(in_ctr python3 -c "$probe" 127.0.0.1)" == open ]] || fail "loopback can't reach 443 with the firewall on"
result="$(docker exec "$CLIENT" python3 -c "$probe" "$CTR_IP")"
[[ "$result" == blocked* ]] || fail "a non-Cloudflare source reached 443: $result"
mkdir -p "$TMP/withclient"
cp "$FIX/ips-v4" "$TMP/withclient/ips-v4"
printf '%s/32\n' "$CLIENT_IP" >> "$TMP/withclient/ips-v4"
cp "$FIX/ips-v6" "$TMP/withclient/ips-v6"
docker cp "$TMP/withclient" "$CTR:/tmp/withclient" >/dev/null
fw apply --ranges-dir /tmp/withclient >/dev/null
result="$(docker exec "$CLIENT" python3 -c "$probe" "$CTR_IP")"
[[ "$result" == open ]] || fail "an allowlisted source can't reach 443: $result"
echo "ok traffic: non-Cloudflare source dropped on 443, loopback allowed, allowlisted source allowed"

fw rollback >/dev/null
for ipt in iptables ip6tables; do
  if in_ctr "$ipt" -S 2>/dev/null | grep -q JDAD-CF; then fail "$ipt still references JDAD-CF after rollback"; fi
  in_ctr "$ipt" -S DOCKER-USER >/dev/null || fail "rollback removed Docker's DOCKER-USER chain"
done
fw rollback >/dev/null
echo "ok rollback removes hooks and chains, keeps DOCKER-USER, and can be re-run"
