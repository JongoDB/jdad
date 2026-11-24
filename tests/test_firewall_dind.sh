#!/usr/bin/env bash
# Opt-in, not part of ./verify: proves deploy/firewall-cloudflare.sh on a
# real Docker-published port (DNAT 443 -> 8443, filtered in DOCKER-USER),
# which tests/test_firewall.sh can't reach. Needs a privileged
# Docker-in-Docker container and network access to pull docker:29-dind,
# busybox and the pinned Python base image. Unique names per run.
#
#   bash tests/test_firewall_dind.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FIX="$ROOT/tests/fixtures/cloudflare"
N="jdad-fwdind-$$-$RANDOM"
C="$N-client"
BASE="$(sed -n 's/^FROM \(python:3.12-slim@sha256:[0-9a-f]*\).*/\1/p' "$ROOT/Dockerfile" | head -1)"
# -v: docker:dind declares VOLUME /var/lib/docker; without it each run leaks an anonymous volume.
trap 'docker rm -f -v "$N" "$C" >/dev/null 2>&1 || true' EXIT

fail() { echo "FAIL $*" >&2; exit 1; }
ip_of() { docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$1"; }
fw() { docker exec -e JDAD_FW_STATE=/tmp/fw "$N" bash /repo/deploy/firewall-cloudflare.sh "$@"; }
probe='import socket,sys
s=socket.socket(); s.settimeout(3)
try:
    s.connect((sys.argv[1], int(sys.argv[2]))); print("open")
except OSError as e:
    print("blocked", type(e).__name__)'
connect() { docker exec "$C" python3 -c "$probe" "$1" "$2"; }

docker run -d --privileged --name "$N" -v "$ROOT:/repo:ro" docker:29-dind >/dev/null
for _ in $(seq 1 60); do docker exec "$N" docker info >/dev/null 2>&1 && break; sleep 1; done
docker exec "$N" sh -c 'apk add -q bash >/dev/null && docker run -d --name web -p 443:8443 busybox:1.37 httpd -f -p 8443 >/dev/null'
docker run -d --name "$C" "$BASE" sleep 300 >/dev/null
DIND_IP="$(ip_of "$N")"
CLIENT_IP="$(ip_of "$C")"
for _ in $(seq 1 20); do [[ "$(connect "$DIND_IP" 443)" == open ]] && break; sleep 0.5; done

[[ "$(connect "$DIND_IP" 443)" == open ]] || fail "published port not reachable before the firewall"
fw apply --ranges-dir /repo/tests/fixtures/cloudflare >/dev/null
[[ "$(connect "$DIND_IP" 443)" == blocked* ]] || fail "non-Cloudflare source reached the published port"
loop="$(docker exec "$N" wget -q -T 3 -O /dev/null http://127.0.0.1:443/ 2>&1 || true)"
[[ "$loop" == *404* ]] || fail "loopback can't reach the published port (expected busybox's 404, got: $loop)"
docker exec "$N" docker run --rm busybox:1.37 wget -q -T 8 -O /dev/null https://github.com \
  || fail "container outbound HTTPS broke (a build's uv sync would fail)"
echo "ok published port: non-Cloudflare source dropped, loopback and container outbound HTTPS still work"

docker exec "$N" mkdir -p /tmp/allow
{ cat "$FIX/ips-v4"; echo "$CLIENT_IP/32"; } | docker exec -i "$N" sh -c 'cat > /tmp/allow/ips-v4'
docker exec -i "$N" sh -c 'cat > /tmp/allow/ips-v6' < "$FIX/ips-v6"
fw apply --ranges-dir /tmp/allow >/dev/null
[[ "$(connect "$DIND_IP" 443)" == open ]] || fail "allowlisted source can't reach the published port"
echo "ok published port: allowlisted source connects"

docker exec "$N" docker restart web >/dev/null
sleep 1
fw apply --ranges-dir /repo/tests/fixtures/cloudflare >/dev/null
docker exec "$N" docker restart web >/dev/null
sleep 1
[[ "$(connect "$DIND_IP" 443)" == blocked* ]] || fail "rules lost after the container restarted"
echo "ok rules survive a container restart"

fw rollback >/dev/null
[[ "$(connect "$DIND_IP" 443)" == open ]] || fail "rollback did not reopen the port"
[[ "$(docker exec "$N" sh -c 'iptables -S; ip6tables -S' | grep -c JDAD-CF || true)" == 0 ]] || fail "JDAD-CF left after rollback"
echo "ok rollback reopens the port and removes every JDAD-CF reference"
