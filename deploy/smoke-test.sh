#!/usr/bin/env bash
# The deploy smoke test (TASK-065): build the three images, start deploy/compose.yml over a throwaway fixture
# data directory, and check, over TLS through Caddy:
#   1. /api/v1/healthz has the index loaded and the web root answers 200 (AC #1);
#   2. the api runs as op-api (uid 10001), not root, and can't write its index or takedown mounts (AC #3);
#   3. index promotion: repoint `current`, SIGHUP, /api/v1/meta reports the new version (AC #2);
#   4. retire: refused for the served version and for one a search record pins, done for one neither
#      (AC #2, TASK-085), and the record store still the API's afterwards;
#   5. a takedown: the listed paper's abstract is withheld, and `op takedown check` (the takedown-check
#      service, as this account, which owns the log) passes;
#   6. no log line holds the query text.
# Run from the repository root: deploy/smoke-test.sh. It needs docker (with compose) and uv, uses its own
# compose project (openproceedings-smoke) so it never touches a running deployment, writes only under a
# mktemp directory and its own volumes, and removes both on exit. Ports: OP_HTTP_PORT and OP_HTTPS_PORT
# (default 80 and 443); the TLS checks connect to https://localhost:$OP_HTTPS_PORT.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

work=$(mktemp -d "${TMPDIR:-/tmp}/openproceedings-smoke.XXXXXX")
export OP_DATA_HOST="$work/data" OP_INSTANCE=private OP_DOMAIN=localhost
export OP_HTTP_PORT="${OP_HTTP_PORT:-80}" OP_HTTPS_PORT="${OP_HTTPS_PORT:-443}"
dc=(docker compose -p openproceedings-smoke -f deploy/compose.yml)
base="https://localhost:$OP_HTTPS_PORT"
query=zzsmokequeryword # must never reach a log line

cleanup() {
  "${dc[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  chmod -R u+w "$work" 2>/dev/null || true
  rm -rf "$work"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  "${dc[@]}" logs --no-color --tail 40 >&2 || true
  exit 1
}

step() { printf '\n== %s\n' "$*"; }

step "fixture data directory"
versions=$(PYTHONPATH=backend uv run --locked python -m tests.deploy.fixture_data "$OP_DATA_HOST")
big=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["big"])' "$versions")
small=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["small"])' "$versions")
spare=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["spare"])' "$versions")
echo "current -> $big; also built $small and $spare"
# one takedown, listed and logged: the log in its own directory outside the data directory, 0700 and 0600
listed=$(head -1 "$OP_DATA_HOST/snapshots/small/records.jsonl" | python3 -c 'import json,sys; print(json.loads(sys.stdin.readline())["id"])')
printf '%s\n' "$listed" >"$OP_DATA_HOST/takedowns/withheld.txt"
export OP_TAKEDOWN_LOG_HOST="$work/takedown-log"
(umask 077 && mkdir "$OP_TAKEDOWN_LOG_HOST" && printf '{"record_id": "%s", "received": "2026-10-02", "requester": "smoke test", "basis": "smoke test", "decision": "withheld", "applied": "2026-10-02", "first_index_version": null}\n' "$listed" >"$OP_TAKEDOWN_LOG_HOST/log.jsonl")
echo "takedown list: $listed"

step "build the images"
"${dc[@]}" build --quiet

# Docker Desktop (macOS, Windows) shares host directories through a file server that keeps the host's own
# owners and modes, so a container can neither change a bind-mounted file's group nor be refused by it: the
# ownership checks (the permission step here and the index write checks in 2) mean something only on Linux
linux=false
[ "$(uname -s)" = Linux ] && linux=true

step "index permissions (deploy/index-permissions.sh, as root in a throwaway container)"
if $linux; then
  for v in "$big" "$small" "$spare"; do
    docker run --rm --user 0:0 --network none --entrypoint sh \
      -v "$OP_DATA_HOST/indexes:/indexes" -v "$PWD/deploy/index-permissions.sh:/index-permissions.sh:ro" \
      openproceedings-api:local /index-permissions.sh /indexes "$v"
  done
else
  echo "skipped: not a Linux host (Docker Desktop keeps host ownership on bind mounts)"
fi

step "docker compose up"
"${dc[@]}" up -d --wait --wait-timeout 180 || fail "the stack did not become healthy"
"${dc[@]}" ps --format '{{.Service}}: {{.Status}}'
cert="$work/caddy-root.crt"
"${dc[@]}" cp caddy:/data/caddy/pki/authorities/local/root.crt "$cert" >/dev/null
curl_tls=(curl -sS --fail --cacert "$cert")

step "1. TLS: healthz and the web root"
health=$("${curl_tls[@]}" "$base/api/v1/healthz") || fail "healthz over TLS"
echo "$health"
grep -q "\"index_loaded\":true,\"index_version\":\"$big\"" <<<"$health" || fail "healthz: index $big not loaded"
status=$("${curl_tls[@]}" -o /dev/null -w '%{http_code}' "$base/") || fail "web root over TLS"
echo "GET / -> $status"
[ "$status" = 200 ] || fail "web root answered $status"
"${curl_tls[@]}" -o /dev/null "$base/api/v1/search?q=$query" || fail "search over TLS"
"${curl_tls[@]}" -o /dev/null "$base/search?q=$query" || fail "search page over TLS"

step "2. the api's user and mounts"
"${dc[@]}" exec -T api id
[ "$("${dc[@]}" exec -T api id -u)" = 10001 ] || fail "api is not uid 10001"
targets=(/data/takedowns/x /data/snapshots/x) # read-only mounts
$linux && targets+=("/data/indexes/$big/x" /data/indexes/x) # refused by ownership and mode
for target in "${targets[@]}"; do
  if "${dc[@]}" exec -T api sh -c "touch $target" 2>/dev/null; then
    fail "api could write $target"
  fi
  echo "api can't write $target"
done
"${dc[@]}" exec -T api sh -c 'ls -A /data/takedowns'

record=$("${curl_tls[@]}" -X POST -H 'content-type: application/json' -d '{"q":"learning"}' "$base/api/v1/records" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["record_id"])') || fail "saving a search record"
echo "saved search record $record on $big"

step "3. promote $small: repoint current, SIGHUP, /meta"
ln -sfn "$small" "$OP_DATA_HOST/indexes/current"
"${dc[@]}" kill -s HUP api >/dev/null
served=""
for _ in $(seq 1 30); do
  served=$("${curl_tls[@]}" "$base/api/v1/meta" | python3 -c 'import json,sys; print(json.load(sys.stdin)["index_version"])')
  [ "$served" = "$small" ] && break
  sleep 1
done
echo "/api/v1/meta index_version: $served"
[ "$served" = "$small" ] || fail "the API still serves $served after SIGHUP"

step "4. retire"
if "${dc[@]}" run --rm ops index retire "$small"; then
  fail "retire of the served $small was not refused"
fi
if "${dc[@]}" run --rm ops index retire "$big"; then
  fail "retire of $big, which record $record pins, was not refused"
fi
"${dc[@]}" run --rm ops index retire "$spare" --dry-run || fail "retire --dry-run of $spare"
"${dc[@]}" run --rm ops index retire "$spare" || fail "retire of $spare"
[ ! -e "$OP_DATA_HOST/indexes/$spare" ] || fail "$spare still exists after retire"
[ -d "$OP_DATA_HOST/indexes/$big" ] || fail "the pinned $big is gone"
"${curl_tls[@]}" "$base/api/v1/healthz" | grep -q "\"index_version\":\"$small\"" || fail "healthz after retire"
replay=$("${curl_tls[@]}" "$base/api/v1/records/$record" | python3 -c 'import json,sys; print(json.load(sys.stdin)["replay"]["status"])') \
  || fail "the record after retire"
echo "record $record on its pinned $big replays: $replay"
[ "$replay" = reproduced ] || fail "record $record replays as $replay, not reproduced"
# the ops container ran as root on the record store: every file there must still be op-api's
owners=$("${dc[@]}" exec -T api sh -c 'stat -c "%u %n" /data/records/*')
echo "$owners"
if grep -qv '^10001 ' <<<"$owners"; then
  fail "a file in the record store is not op-api's after retire"
fi
"${curl_tls[@]}" -o /dev/null -X POST -H 'content-type: application/json' -d '{"q":"model"}' "$base/api/v1/records" \
  || fail "saving a search record after retire"
echo "retired $spare; $small still served; the store still takes saves"

step "5. the takedown"
withheld=$("${curl_tls[@]}" "$base/api/v1/papers/$listed" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["abstract_withheld"], d["paper"].get("abstract"))') \
  || fail "GET /papers/$listed"
echo "/api/v1/papers/$listed: abstract_withheld, abstract = $withheld"
[ "$withheld" = "True None" ] || fail "the listed abstract is served"
"${dc[@]}" run --rm --user "$(id -u):$(id -g)" takedown-check || fail "op takedown check"

step "6. no query text in any log"
if "${dc[@]}" logs --no-color | grep -q "$query"; then
  fail "a log line holds the query text"
fi
echo "no log line holds the query"

printf '\nPASS\n'
