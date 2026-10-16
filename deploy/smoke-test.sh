#!/usr/bin/env bash
# The deploy smoke test (TASK-065): build the three images, start deploy/compose.yml over a throwaway fixture
# data directory, and check, over TLS through Caddy:
#   1. /api/v1/healthz has the index loaded and the web root answers 200 (AC #1);
#   2. the api runs as op-api (uid 10001; this script pins OP_API_UID/OP_API_GID), not root; its takedown and snapshot mounts are read-only, its
#      takedown directory holds only withheld.txt, and (on Linux) file modes refuse it any write in indexes/
#      (AC #3);
#   3. index promotion: repoint `current`, SIGHUP, /api/v1/meta reports the new version (AC #2);
#   4. retire: refused for the served version and for one a search record pins, each for that reason, and
#      done for one neither; on Linux, refused on the host too (the record store is the API's); the pinned
#      record still replays `reproduced`; the record store still the API's and taking saves; a backup of it
#      opens (AC #2, TASK-085);
#   5. a takedown: the listed paper's abstract (it has one) is withheld while a neighbour's is served, and
#      `op takedown check` (the takedown-check service, as this account, which owns the log) passes;
#   6. comparisons: without --compare, /meta offers none. With --compare (which adds deploy/compare.yml;
#      TASK-183): compare.yml's api command is compose.yml's plus --compare; caddy has a memory limit; through
#      the proxy, while OP_SMOKE_STALLS uploads (default 8) that stop a byte short of 16 MiB are held, a whole
#      16 MiB file is compared; the stalled ones never reach the API and are cut at read_body; the proxy's
#      memory peak is printed and must stay under its limit with no OOM kill; a file one byte over 16 MiB is
#      413, and one sent without a length (chunked, or HTTP/2 unsized) 411. Either way, every other path keeps
#      the 64 KiB cap;
#   7. no log line holds the query text.
# Run from the repository root: deploy/smoke-test.sh [--compare]. It needs docker (with compose) and uv. It uses its own
# compose project (openproceedings-smoke) and its own image tag (smoke-<pid>), so it never touches a running
# deployment or the images it runs; it writes only under a mktemp directory, and removes that directory, its
# containers, networks, volumes and images on exit. Ports: OP_HTTP_PORT and OP_HTTPS_PORT (default
# 127.0.0.1:80 and 127.0.0.1:443: loopback only; an address is optional, as in compose.yml); the TLS checks
# connect to https://localhost:<the port>.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

compare=false
case "${1:-}" in
  "") ;;
  --compare) compare=true ;;
  *)
    echo "usage: deploy/smoke-test.sh [--compare]" >&2
    exit 2
    ;;
esac

work=$(mktemp -d "${TMPDIR:-/tmp}/openproceedings-smoke.XXXXXX")
export OP_DATA_HOST="$work/data" OP_INSTANCE=private OP_DOMAIN=localhost OP_IMAGE_TAG="smoke-$$"
# the API's ids, pinned here (the shell's environment wins over a deploy/.env compose would otherwise read)
export OP_API_UID=10001 OP_API_GID=10001
export OP_HTTP_PORT="${OP_HTTP_PORT:-127.0.0.1:80}" OP_HTTPS_PORT="${OP_HTTPS_PORT:-127.0.0.1:443}"
dc=(docker compose -p openproceedings-smoke -f deploy/compose.yml)
if $compare; then dc+=(-f deploy/compare.yml); fi
api_image="openproceedings-api:$OP_IMAGE_TAG"
https_port=${OP_HTTPS_PORT##*:}
base="https://localhost:$https_port"
query=zzsmokequeryword # must never reach a log line

# Docker Desktop (macOS, Windows) shares host directories through a file server that keeps the host's own
# owners and modes, so a container can neither change a bind-mounted file's owner or group nor be refused by
# them: the ownership steps and checks below run only on Linux
linux=false
[ "$(uname -s)" = Linux ] && linux=true

# as root in a throwaway container of the api image (no network, never a pulled image): what an operator
# does with sudo. Usage: as_root '<sh script using "$1"…>' <args…> (paths go in as arguments, never into
# the script text)
as_root() {
  local script=$1
  shift
  docker run --pull never --rm --user 0:0 --network none --entrypoint sh -v "$work:$work" \
    -v "$PWD/deploy/index-permissions.sh:/index-permissions.sh:ro" "$api_image" -c "$script" sh "$@"
}

stalls_pid=
cleanup() {
  if [ -n "$stalls_pid" ]; then kill "$stalls_pid" 2>/dev/null || true; fi # the stalled uploads' probe
  "${dc[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  # shellcheck disable=SC2016 # "$1" expands inside the container's sh, on purpose
  if $linux; then as_root 'rm -rf "$1"' "$work/data/records" >/dev/null 2>&1 || true; fi # op-api's, 0700
  docker image rm "openproceedings-api:$OP_IMAGE_TAG" "openproceedings-web:$OP_IMAGE_TAG" \
    "openproceedings-caddy:$OP_IMAGE_TAG" >/dev/null 2>&1 || true
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

json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

engine=$(docker version --format '{{.Server.Version}}')
echo "Docker Engine $engine"
python3 - "$engine" <<'PY' || echo "WARNING: Docker Engine $engine predates the fix for CVE-2024-29018 (26.0.0, 25.0.4, 23.0.11): its internal networks can resolve names outside (deploy/compose.yml)"
import re, sys
v = tuple(int(x) for x in re.findall(r"\d+", sys.argv[1])[:3])
sys.exit(0 if v >= (26, 0, 0) or (25, 0, 4) <= v < (26,) or (23, 0, 11) <= v < (24,) else 1)
PY

step "fixture data directory"
versions=$(PYTHONPATH=backend uv run --locked python -m tests.deploy.fixture_data "$OP_DATA_HOST")
big=$(json 'd["big"]' <<<"$versions")
small=$(json 'd["small"]' <<<"$versions")
spare=$(json 'd["spare"]' <<<"$versions")
echo "current -> $big; also built $small and $spare"
# one takedown, of a paper that has an abstract (so withholding it shows), listed and logged: the log in its
# own directory outside the data directory, 0700 and 0600. A neighbour with an abstract stays unlisted.
read -r listed neighbour < <(python3 -c '
import json, sys
ids = [r["id"] for r in map(json.loads, open(sys.argv[1], encoding="utf-8")) if r.get("abstract")]
print(ids[0], ids[1])' "$OP_DATA_HOST/snapshots/small/records.jsonl") \
  || fail "the fixture has fewer than two records with abstracts"
printf '%s\n' "$listed" >"$OP_DATA_HOST/takedowns/withheld.txt"
export OP_TAKEDOWN_LOG_HOST="$work/takedown-log"
(umask 077 && mkdir "$OP_TAKEDOWN_LOG_HOST" && printf '{"record_id": "%s", "received": "2026-10-02", "requester": "smoke test", "basis": "smoke test", "decision": "withheld", "applied": "2026-10-02", "first_index_version": null}\n' "$listed" >"$OP_TAKEDOWN_LOG_HOST/log.jsonl")
echo "takedown list: $listed (unlisted neighbour: $neighbour)"

step "build the images ($OP_IMAGE_TAG)"
"${dc[@]}" build --quiet

step "host setup: the record store and index permissions (as root, as an operator would with sudo)"
# index-permissions.sh must refuse to run without an explicit gid (no default that may be another account's)
if out=$(sh deploy/index-permissions.sh "$OP_DATA_HOST/indexes" "$big" 2>&1); then
  fail "index-permissions.sh ran without a gid"
fi
grep -qF "usage:" <<<"$out" || fail "index-permissions.sh without a gid failed for another reason: $out"
echo "index-permissions.sh without a gid: refused (usage)"
if $linux; then
  # shellcheck disable=SC2016 # "$1" expands inside the container's sh, on purpose
  as_root 'install -d -o "$2" -g "$3" -m 0700 "$1"' "$OP_DATA_HOST/records" "$OP_API_UID" "$OP_API_GID"
  for v in "$big" "$small" "$spare"; do
    # shellcheck disable=SC2016 # "$1" expands inside the container's sh, on purpose
    as_root '/index-permissions.sh "$1" "$2" "$3"' "$OP_DATA_HOST/indexes" "$v" "$OP_API_GID"
  done
else
  mkdir -m 0700 "$OP_DATA_HOST/records"
  echo "index permissions skipped: not a Linux host (Docker Desktop keeps host ownership on bind mounts)"
fi

step "docker compose up"
"${dc[@]}" up -d --wait --wait-timeout 180 || fail "the stack did not become healthy"
"${dc[@]}" ps --format '{{.Service}}: {{.Status}}'
cert="$work/caddy-root.crt"
for _ in $(seq 1 20); do # Caddy writes its local CA's root at startup
  "${dc[@]}" cp caddy:/data/caddy/pki/authorities/local/root.crt "$cert" >/dev/null 2>&1 && break
  sleep 1
done
[ -s "$cert" ] || fail "Caddy's local CA root never appeared"
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
[ "$("${dc[@]}" exec -T api id -u)" = "$OP_API_UID" ] || fail "api is not uid $OP_API_UID"
# each write must be refused for its own reason: a missing mount or directory would fail differently
refused() { # <target> <expected error>
  local err
  if err=$("${dc[@]}" exec -T api sh -c "touch $1" 2>&1); then fail "api could write $1"; fi
  grep -qF "$2" <<<"$err" || fail "writing $1 failed, but not with '$2': $err"
  echo "api can't write $1: $2"
}
refused /data/takedowns/x "Read-only file system"
refused /data/snapshots/x "Read-only file system"
if $linux; then
  refused "/data/indexes/$big/x" "Permission denied"
  refused /data/indexes/x "Permission denied"
fi
listing=$("${dc[@]}" exec -T api ls -A /data/takedowns)
echo "/data/takedowns holds: $listing"
[ "$listing" = withheld.txt ] || fail "the api's takedown directory holds more than withheld.txt"

record=$("${curl_tls[@]}" -X POST -H 'content-type: application/json' -d '{"q":"learning"}' "$base/api/v1/records" \
  | json 'd["record_id"]') || fail "saving a search record"
echo "saved search record $record on $big"

step "3. promote $small: repoint current, SIGHUP, /meta"
ln -sfn "$small" "$OP_DATA_HOST/indexes/current"
"${dc[@]}" kill -s HUP api >/dev/null
served=""
for _ in $(seq 1 30); do
  served=$("${curl_tls[@]}" "$base/api/v1/meta" | json 'd["index_version"]') || true
  [ "$served" = "$small" ] && break
  sleep 1
done
echo "/api/v1/meta index_version: $served"
[ "$served" = "$small" ] || fail "the API still serves $served after SIGHUP"

step "4. retire"
refused_retire() { # <index_version> <expected stderr> <why>
  local out
  if out=$("${dc[@]}" run --rm ops index retire "$1" 2>&1); then fail "retire of $1 ($3) was not refused"; fi
  grep -qF "$2" <<<"$out" || fail "retire of $1 was refused, but not because $3: $out"
  echo "retire $1 refused: $3"
}
refused_retire "$small" "\`current\` points at $small" "current points at it"
refused_retire "$big" "1 search record pins $big" "a search record pins it"
if $linux; then # on the host, as this account: the record store is op-api's 0700, so it can't count pins
  out=$(PYTHONPATH=backend uv run --locked op --data-dir "$OP_DATA_HOST" index retire "$spare" --dry-run 2>&1) \
    && fail "retire on the host was not refused: $out"
  grep -qF "search-record store can't be read" <<<"$out" || fail "retire on the host refused for another reason: $out"
  echo "retire $spare on the host refused: the record store can't be read"
fi
"${dc[@]}" run --rm ops index retire "$spare" --dry-run || fail "retire --dry-run of $spare"
"${dc[@]}" run --rm ops index retire "$spare" || fail "retire of $spare"
[ ! -e "$OP_DATA_HOST/indexes/$spare" ] || fail "$spare still exists after retire"
[ -d "$OP_DATA_HOST/indexes/$big" ] || fail "the pinned $big is gone"
health=$("${curl_tls[@]}" "$base/api/v1/healthz") || fail "healthz after retire"
grep -q "\"index_version\":\"$small\"" <<<"$health" || fail "healthz after retire: $health"
replay=$("${curl_tls[@]}" "$base/api/v1/records/$record" | json 'd["replay"]["status"]') || fail "the record after retire"
echo "record $record on its pinned $big replays: $replay"
[ "$replay" = reproduced ] || fail "record $record replays as $replay, not reproduced"
# the ops container ran as root on the record store: every file there must still be op-api's (Linux only:
# Docker Desktop reports its file server's owner, not the file's)
if $linux; then
  owners=$("${dc[@]}" exec -T api sh -c 'stat -c "%u %n" /data/records/*')
  echo "$owners"
  if grep -qv "^$OP_API_UID " <<<"$owners"; then
    fail "a file in the record store is not op-api's after retire"
  fi
fi
"${curl_tls[@]}" -o /dev/null -X POST -H 'content-type: application/json' -d '{"q":"model"}' "$base/api/v1/records" \
  || fail "saving a search record after retire"
echo "retired $spare; $small still served; the store still takes saves"
# the runbook's backup (deploy/README.md §Backups): a consistent copy streamed out, which must open
"${dc[@]}" exec -T api python -c "$(cat <<'PY'
import sqlite3, sys, tempfile
with tempfile.NamedTemporaryFile(dir="/tmp") as f:
    sqlite3.connect("/data/records/records.sqlite").backup(sqlite3.connect(f.name))
    sys.stdout.buffer.write(open(f.name, "rb").read())
PY
)" >"$work/records-backup.sqlite" || fail "backing up the record store"
saved=$(python3 -c 'import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute("select count(*) from records").fetchone()[0])' \
  "$work/records-backup.sqlite") || fail "the backup doesn't open"
echo "backup: $saved search records"
[ "$saved" = 2 ] || fail "the backup holds $saved records, not 2"

step "5. the takedown"
shown=$("${curl_tls[@]}" "$base/api/v1/papers/$listed" | json 'd["abstract_withheld"], d["paper"].get("abstract")') \
  || fail "GET /papers/$listed"
echo "/api/v1/papers/$listed: abstract_withheld, abstract = $shown"
[ "$shown" = "True None" ] || fail "the listed abstract is served"
shown=$("${curl_tls[@]}" "$base/api/v1/papers/$neighbour" | json 'd["abstract_withheld"], bool(d["paper"].get("abstract"))') \
  || fail "GET /papers/$neighbour"
echo "/api/v1/papers/$neighbour (unlisted): abstract_withheld, has an abstract = $shown"
[ "$shown" = "False True" ] || fail "the unlisted neighbour's abstract is not served"
"${dc[@]}" run --rm --user "$(id -u):$(id -g)" takedown-check || fail "op takedown check"

step "6. comparisons"
offered=$("${curl_tls[@]}" "$base/api/v1/meta" | json '(d["limits"]["compare"] or {}).get("max_body_bytes")') \
  || fail "GET /meta"
echo "/meta limits.compare.max_body_bytes: $offered"
# a status from curl without --fail: the refusals below are the point
status_of() { curl -sS --cacert "$cert" -o /dev/null -w '%{http_code}' "$@" || true; }
head -c 65537 /dev/zero | tr '\0' x >"$work/over64k.json"
# the proxy's own body caps and protocols, as Caddy adapted the Caddyfile in the running container: a body
# that declares its length over 64 KiB is refused by the API from the header whatever the proxy does, so the
# 413 below can't show the proxy's cap
"${dc[@]}" exec -T caddy caddy adapt --config /etc/caddy/Caddyfile 2>/dev/null | python3 -c '
import json, sys
on = sys.argv[1] == "true"
srv = next(s for s in json.load(sys.stdin)["apps"]["http"]["servers"].values() if ":443" in s.get("listen", []))
site = srv["routes"][0]["handle"][0]["routes"]
caps = [(r.get("match"), h["max_size"]) for r in site for h in r.get("handle", []) if h["handler"] == "request_body"]
compare = [r["handle"][0]["routes"] for r in site if r.get("match") == [{"path": ["/api/v1/compare"]}]]
inner = [(h["handler"], h.get("max_size") or h.get("request_buffers") or h.get("status_code"), r.get("match"))
         for routes in compare for r in routes for h in r["handle"]]
want_inner = [("request_body", 16777216, None),
              ("static_response", 411, [{"method": ["POST"], "not": [{"header": {"Content-Length": ["*"]}}]}]),
              ("reverse_proxy", 16777216, None)]
print("proxy: protocols", srv.get("protocols"), "| body caps", caps, "| /api/v1/compare", inner)
ok = (srv.get("protocols") == ["h1", "h2"] and caps == [([{"not": [{"path": ["/api/v1/compare"]}]}], 65536)]
      and sorted(map(str, inner)) == sorted(map(str, want_inner))) if on else (
      srv.get("protocols") == ["h1", "h2", "h3"] and caps == [(None, 65536)] and not compare)
sys.exit(0 if ok else 1)' "$compare" || fail "the proxy's adapted body caps or protocols are not what compare=$compare needs"
# HTTP/3 is advertised (Alt-Svc) only with comparisons off: Caddy doesn't give its HTTP/3 server read_body
h3=$("${curl_tls[@]}" -D - -o /dev/null "$base/api/v1/healthz" | grep -ci '^alt-svc: h3' || true)
echo "Alt-Svc h3 headers: $h3"
if ! $compare; then
  [ "$offered" = None ] || fail "comparisons are offered without deploy/compare.yml"
  [ "$h3" = 1 ] || fail "the proxy doesn't advertise HTTP/3 with comparisons off"
else
  [ "$h3" = 0 ] || fail "the proxy still advertises HTTP/3 with comparisons on"
  [ "$offered" = 16777216 ] || fail "comparisons on, but /meta offers $offered"
  # compare.yml repeats compose.yml's api command (compose replaces a list): it must be that plus --compare
  python3 -c '
import json, sys
base, on = (json.load(open(f))["services"]["api"]["command"] for f in sys.argv[1:])
print("api command:", " ".join(on))
sys.exit(0 if on == [*base, "--compare"] else 1)' \
    <(docker compose -f deploy/compose.yml config --format json) \
    <(docker compose -f deploy/compose.yml -f deploy/compare.yml config --format json) \
    || fail "deploy/compare.yml's api command is not compose.yml's plus --compare"
  # cgroup v2 (memory.max); memory.peak needs Linux 5.19 or later, else the peak is sampled while uploads are held
  mem() { "${dc[@]}" exec -T caddy cat "/sys/fs/cgroup/$1"; }
  read_body=$("${dc[@]}" exec -T caddy printenv OP_READ_BODY) || fail "reading caddy's OP_READ_BODY"
  case "$read_body" in
    *[!0-9]*s | s | *[!s]) fail "this test reads OP_READ_BODY in whole seconds (60s), not '$read_body'" ;;
  esac
  limit=$(mem memory.max) || fail "reading caddy's memory limit (cgroup v2)"
  echo "caddy: read_body $read_body, memory limit $limit bytes, GOMEMLIMIT $("${dc[@]}" exec -T caddy printenv GOMEMLIMIT)"
  [ "$limit" != max ] || fail "the caddy service has no memory limit"
  caddy_id=$("${dc[@]}" ps -q caddy)
  compared() { "${dc[@]}" logs --no-color api | grep -c '"route": "/api/v1/compare"' || true; }
  records=$(python3 backend/tests/deploy/compare_probe.py ris "$OP_DATA_HOST/snapshots/small/records.jsonl" 16777216 \
    "$work/full.ris") || fail "writing the 16 MiB RIS file"
  stalls=${OP_SMOKE_STALLS:-8}
  before=$(compared)
  # uploads that stop one byte short of their end, all at once: the proxy must hold each whole
  probe=(python3 backend/tests/deploy/compare_probe.py stall "$https_port" "$cert" "/api/v1/compare?q=$query")
  "${probe[@]}" 16777216 16777215 "$stalls" >"$work/stalls.out" &
  stalls_pid=$!
  for _ in $(seq 1 120); do
    grep -q sent "$work/stalls.out" && break
    sleep 1
  done
  grep -q sent "$work/stalls.out" || fail "the stalled uploads never finished sending"
  held=$(mem memory.current) || fail "reading caddy's memory"
  echo "$stalls uploads stalled a byte short; proxy memory now $((held / 1048576)) MiB"
  # the API's one comparison slot is free while the proxy holds them: a whole 16 MiB file is compared
  answer=$("${curl_tls[@]}" -H 'content-type: application/x-research-info-systems' --data-binary "@$work/full.ris" \
    "$base/api/v1/compare?q=learning" | json 'd["records_total"], d["papers_total"]') \
    || fail "a 16 MiB comparison while uploads stall"
  echo "a 16 MiB comparison while they stall: records, papers = $answer"
  [ "$answer" = "$records $records" ] || fail "the 16 MiB comparison of $records records read $answer"
  now=$(mem memory.current) || fail "reading caddy's memory"
  [ "$now" -gt "$held" ] && held=$now
  wait "$stalls_pid" || fail "the stalled uploads"
  stalls_pid=
  echo "stalled uploads, seconds from each request's start: $(tail -1 "$work/stalls.out")"
  python3 -c '
import json, sys
cut = json.loads(open(sys.argv[2]).read().splitlines()[-1])
limit = float(sys.argv[1])
sys.exit(0 if abs(cut["cut_min_s"] - limit) <= 2 and abs(cut["cut_max_s"] - limit) <= 2 else 1)' \
    "${read_body%s}" "$work/stalls.out" || fail "a stalled upload was not cut at read_body ($read_body)"
  peak=$(mem memory.peak 2>/dev/null) || peak=$held # sampled: no memory.peak before Linux 5.19
  oom=$(mem memory.events | sed -n 's/^oom_kill //p') || fail "reading caddy's OOM kills"
  restarts=$(docker inspect --format '{{.RestartCount}}' "$caddy_id") || fail "reading caddy's restarts"
  echo "proxy memory peak $((peak / 1048576)) MiB of $((limit / 1048576)) MiB; oom_kill $oom; restarts $restarts"
  [ "$oom" = 0 ] && [ "$restarts" = 0 ] && [ "$("${dc[@]}" ps -q caddy)" = "$caddy_id" ] \
    || fail "the proxy was killed (over its memory limit?)"
  after=$(compared)
  echo "API compare requests: $((after - before)) (the 16 MiB comparison; no stalled upload reached the API)"
  [ "$((after - before))" = 1 ] || fail "a stalled upload reached the API"
  head -c 16777217 /dev/zero | tr '\0' x >"$work/over.ris"
  status=$(status_of -H 'content-type: application/x-research-info-systems' --data-binary "@$work/over.ris" \
    "$base/api/v1/compare?q=$query")
  echo "16 MiB + 1 byte to /api/v1/compare -> $status (the API's, from the declared length)"
  [ "$status" = 413 ] || fail "a file one byte over 16 MiB answered $status"
  # past request_buffers the proxy streams the rest to the API, so a file must say how long it is
  status=$(status_of --http1.1 -H 'Transfer-Encoding: chunked' -H 'content-type: application/x-research-info-systems' \
    --data-binary "@$work/over64k.json" "$base/api/v1/compare?q=$query")
  echo "a chunked file to /api/v1/compare -> $status"
  [ "$status" = 411 ] || fail "a chunked file answered $status"
  status=$(status_of --http2 -X POST -T - -H 'content-type: application/x-research-info-systems' \
    "$base/api/v1/compare?q=$query" <"$work/over64k.json")
  echo "an HTTP/2 file with no content-length to /api/v1/compare -> $status"
  [ "$status" = 411 ] || fail "an unsized HTTP/2 file answered $status"
fi
# every other path still refuses a body over 64 KiB (the API's 413, from the declared length; the proxy's own
# cap is the adapted config above)
status=$(status_of -H 'content-type: application/json' --data-binary "@$work/over64k.json" "$base/api/v1/records")
echo "64 KiB + 1 byte to /api/v1/records -> $status"
[ "$status" = 413 ] || fail "a body one byte over 64 KiB to /api/v1/records answered $status"

step "7. no query text in any log"
"${dc[@]}" logs --no-color >"$work/logs.txt" 2>&1 || fail "reading the logs"
[ -s "$work/logs.txt" ] || fail "no logs to check"
if grep -qF -- "$query" "$work/logs.txt"; then
  fail "a log line holds the query text"
fi
echo "no log line holds the query ($(wc -l <"$work/logs.txt" | tr -d ' ') lines checked)"

printf '\nPASS\n'
