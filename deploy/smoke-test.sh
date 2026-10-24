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
#      16 MiB file is compared; the stalled ones never reach the API and are cut at read_body; two batches as
#      large over HTTP/3, trickling a byte a second, are cut at read_body too and get no comparison (TASK-257);
#      the proxy's memory peak is printed and must stay under its limit with no OOM kill, the second HTTP/3
#      batch raising it by less than 25 MiB an upload; a file one byte over 16 MiB is 413, and one sent without
#      a length (chunked, or HTTP/2 unsized) 411. Either way, every other request keeps the 64 KiB cap, refused by the
#      proxy before the API holds a connection for it: a declared length one byte over is the proxy's 413 in
#      the API's own words, 20 times over HTTP/1.1 and HTTP/2 (TASK-259); a chunked body is 411, a PUT to
#      /api/v1/compare included (TASK-268), which with a length gets the API's own 405; an unsized HTTP/2 body
#      over the cap is 413, and one that stops at the cap holds no API connection (TASK-255); a chunked body
#      to the web app that stalls holds no connection to it; the proxy's own 413 on a web path and its 502
#      while web is stopped carry HSTS and no Server header;
#   7. no log line holds the query text.
# Run from the repository root: deploy/smoke-test.sh [--compare]. It needs docker (with compose) and uv. It uses its own
# compose project (OP_SMOKE_PROJECT, default openproceedings-smoke), its own image tag (smoke-<pid>) and its own
# internal network (172.30.81.0/24: compose.yml's default 172.30.80.0/24 is a running deployment's, and Docker
# refuses a second network that overlaps it), so it never touches a running deployment or the images it runs;
# it writes only under a mktemp directory, and removes that directory, its containers, networks, volumes and
# images on exit. Ports: OP_HTTP_PORT and OP_HTTPS_PORT (default
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
# and the internal network: never the default, which a running deployment on this host has
export OP_INTERNAL_SUBNET=172.30.81.0/24 OP_INTERNAL_IP_RANGE=172.30.81.128/25 OP_PROXY_ADDRESS=172.30.81.2
export OP_HTTP_PORT="${OP_HTTP_PORT:-127.0.0.1:80}" OP_HTTPS_PORT="${OP_HTTPS_PORT:-127.0.0.1:443}"
project=${OP_SMOKE_PROJECT:-openproceedings-smoke}
dc=(docker compose -p "$project" -f deploy/compose.yml)
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
    "openproceedings-caddy:$OP_IMAGE_TAG" "openproceedings-smoke-h3:$OP_IMAGE_TAG" >/dev/null 2>&1 || true
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
# a status from curl without --fail: the refusals below are the point. The body goes to $work/answer
status_of() { curl -sS --cacert "$cert" -o "$work/answer" -w '%{http_code}' "$@" || true; }
head -c 65537 /dev/zero | tr '\0' x >"$work/over64k.json"
# the proxy's own body caps, refusals and protocols, as Caddy adapted the Caddyfile in the running container
"${dc[@]}" exec -T caddy caddy adapt --config /etc/caddy/Caddyfile 2>/dev/null | python3 -c '
import json, sys
on = sys.argv[1] == "true"
srv = next(s for s in json.load(sys.stdin)["apps"]["http"]["servers"].values() if ":443" in s.get("listen", []))
site = [(r.get("match"), h) for r in srv["routes"][0]["handle"][0]["routes"] for h in r.get("handle", [])]
caps = [(m, h["max_size"]) for m, h in site if h["handler"] == "request_body"]
post = [{"method": ["POST"], "path": ["/api/v1/compare"]}]
compare = [h["routes"] for m, h in site if m == post]
api = [h.get("request_buffers") for m, h in site if m == [{"path": ["/api/*"]}]]
refusals = [(h["handler"], h["status_code"], m) for m, h in site if h["handler"] in ("error", "static_response")]
length = "string({http.request.header.Content-Length})"
want_refusals = [("error", 413, [{"expression": f"{length}.matches(\x27^0*[0-9]{{1,18}}$\x27) && int({length}) > 65536"}]),
                 ("static_response", 411, [{"header": {"Transfer-Encoding": ["*"]}, "path": ["/api/*"]}])]
envelope = "API_BODY_TOO_LARGE" in json.dumps(srv.get("errors"))
inner = [(h["handler"], h.get("max_size") or h.get("request_buffers") or h.get("status_code"), r.get("match"))
         for routes in compare for r in routes for h in r["handle"]]
want_inner = [("request_body", 16777216, None),
              ("static_response", 411, [{"not": [{"header": {"Content-Length": ["*"]}}]}]),
              ("static_response", 400, [{"expression": {"name": "badlength",
               "expr": f"!{length}.matches(\x27^0*[0-9]{{1,18}}$\x27)"}}]),
              ("static_response", 413, [{"expression": f"int(\x270\x27 + {length}) > 16777216"}]),
              ("reverse_proxy", 16777216, None)]
print("proxy: protocols", srv.get("protocols"), "| body caps", caps, "| /api/* buffers", api, "| refusals",
      refusals, "| 413 in the API envelope", envelope, "| POST /api/v1/compare", inner)
ok = (srv.get("protocols") == ["h1", "h2", "h3"] and api == [65537] and refusals == want_refusals and envelope
      and ((inner == want_inner and caps == [([{"not": post}], 65536)]) if on else (caps == [(None, 65536)] and not compare)))
sys.exit(0 if ok else 1)' "$compare" || fail "the proxy's adapted body caps, refusals or protocols are not what compare=$compare needs"
# HTTP/3 is advertised (Alt-Svc) with comparisons on or off: a stalled upload over QUIC is cut at read_body
# (TASK-257; the --compare run checks it below)
headers=$("${curl_tls[@]}" -D - -o /dev/null "$base/api/v1/healthz") || fail "GET /api/v1/healthz headers"
h3=$(grep -ci '^alt-svc: h3' <<<"$headers" || true)
echo "Alt-Svc h3 headers: $h3"
[ "$h3" = 1 ] || fail "the proxy doesn't advertise HTTP/3"
if ! $compare; then
  [ "$offered" = None ] || fail "comparisons are offered without deploy/compare.yml"
else
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
    "" | *[!0-9]*s | s | *[!s]) fail "this test reads OP_READ_BODY in whole seconds (60s), not '$read_body'" ;;
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
    kill -0 "$stalls_pid" 2>/dev/null || break # it gave up before they had all sent
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
  if [ "$oom" != 0 ] || [ "$restarts" != 0 ] || [ "$("${dc[@]}" ps -q caddy)" != "$caddy_id" ]; then
    fail "the proxy was killed (over its memory limit?)"
  fi
  after=$(compared)
  echo "API compare requests: $((after - before)) (the 16 MiB comparison; no stalled upload reached the API)"
  [ "$((after - before))" = 1 ] || fail "a stalled upload reached the API"
  # two batches as large over HTTP/3 once those are cut (TASK-257), from a container on the stack's edge
  # network to caddy:443 over UDP: each upload sends 16 MiB less 1,216 bytes and then a byte a second, so that
  # QUIC's own 30 s idle timeout never ends it first. Caddy's access log (these are the only HTTP/3 POSTs here)
  # must show each cut at read_body; after the cut the proxy forwards what it read, which the API refuses (408,
  # or 429 while another comparison runs or the client's bucket is empty), so none may get a comparison; and
  # the second batch, sent once the first is cut, must raise the proxy's memory peak by less than 25 MiB an
  # upload (memory.current is no evidence: Go keeps what it freed)
  h3_image="openproceedings-smoke-h3:$OP_IMAGE_TAG"
  docker build --quiet -t "$h3_image" - <deploy/smoke-h3.Dockerfile >/dev/null || fail "building the HTTP/3 client"
  h3_batch() {
    # shellcheck disable=SC2016 # "$1"…"$3" expand inside the container's bash, on purpose
    docker run --rm --network "${project}_edge" -v "$cert:/ca.crt:ro" "$h3_image" bash -c '
for _ in $(seq 1 "$1"); do
  (head -c 16776000 /dev/zero | tr "\0" x; while printf x; do sleep 1; done) | timeout "$3" curl -sS --http3-only \
    -X POST -T - -H "Content-Length: 16777216" -H "content-type: application/x-research-info-systems" \
    --cacert /ca.crt --connect-to localhost:443:caddy:443 -o /dev/null -w "%{http_version} %{http_code}\n" \
    "https://localhost/api/v1/compare?q=$2" &
done
wait' sh "$stalls" "$query" "$((${read_body%s} + 60))" >"$work/h3.out" 2>&1 || true
    echo "HTTP/3 batch $1, version and status each client saw: $(sort "$work/h3.out" | uniq -c | tr -s ' \n' ' ')"
  }
  before=$(compared)
  h3_batch 1
  peak_between=$(mem memory.peak 2>/dev/null) || peak_between=
  h3_batch 2
  "${dc[@]}" logs --no-color caddy | python3 -c '
import json, sys
limit, n = float(sys.argv[1]), int(sys.argv[2])
cuts = []
for line in sys.stdin:
    try:
        d = json.loads(line.partition("| ")[2])
    except ValueError:
        continue
    r = d.get("request") or {}
    if d.get("logger", "").startswith("http.log.access") and r.get("proto") == "HTTP/3.0" and r.get("method") == "POST":
        cuts.append((round(d["duration"], 2), d["status"], d.get("bytes_read")))
print("HTTP/3 uploads in the access log (seconds, status, bytes read):", sorted(cuts))
sys.exit(0 if len(cuts) == n and all(abs(c[0] - limit) <= 2 for c in cuts) else 1)' "${read_body%s}" "$((2 * stalls))" \
    || fail "an HTTP/3 upload was not cut at read_body ($read_body)"
  answers=$("${dc[@]}" logs --no-color api | grep '"route": "/api/v1/compare"' | tail -n +"$((before + 1))" \
    | grep -o '"status": [0-9]*' | sort | uniq -c | tr -s ' \n' ' ' || true)
  echo "the API's answers to them after the cut: ${answers:-none}"
  if grep -q '"status": 200' <<<"$answers"; then fail "a cut HTTP/3 upload was compared"; fi
  if [ -n "$peak_between" ]; then
    peak=$(mem memory.peak) || fail "reading caddy's memory peak"
    echo "proxy memory peak $((peak_between / 1048576)) MiB after the first HTTP/3 batch, $((peak / 1048576)) MiB after the second"
    [ "$((peak - peak_between))" -lt "$((stalls * 25 * 1048576))" ] \
      || fail "the second HTTP/3 batch raised the proxy's memory peak by $(((peak - peak_between) / 1048576)) MiB"
  fi
  oom=$(mem memory.events | sed -n 's/^oom_kill //p') || fail "reading caddy's OOM kills"
  restarts=$(docker inspect --format '{{.RestartCount}}' "$caddy_id") || fail "reading caddy's restarts"
  if [ "$oom" != 0 ] || [ "$restarts" != 0 ] || [ "$("${dc[@]}" ps -q caddy)" != "$caddy_id" ]; then
    fail "the proxy was killed during the HTTP/3 uploads (over its memory limit?)"
  fi
  head -c 16777217 /dev/zero | tr '\0' x >"$work/over.ris"
  status=$(status_of -H 'content-type: application/x-research-info-systems' --data-binary "@$work/over.ris" \
    "$base/api/v1/compare?q=$query")
  echo "16 MiB + 1 byte to /api/v1/compare -> $status: $(cat "$work/answer")"
  if [ "$status" != 413 ] || ! grep -qF 'The file is over 16 MiB' "$work/answer"; then
    fail "a file one byte over 16 MiB was not refused by the proxy (its 413 and text): $status"
  fi
  status=$(status_of --http2 -X POST -H 'Content-Length: abc' -H 'content-type: application/x-research-info-systems' \
    "$base/api/v1/compare?q=$query")
  echo "an HTTP/2 file with Content-Length: abc to /api/v1/compare -> $status"
  [ "$status" = 400 ] || fail "a malformed length answered $status"
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
# every other request keeps the API's 64 KiB cap, and the proxy refuses what is over it before the API holds a
# connection for it. A declared length over the cap is the proxy's 413 from the header, in the API's own words
# (read here from the API itself): forwarded, the API's refusal raced the proxy's sending and once reached the
# client as a 502 (TASK-259), so 20 tries over each protocol
api_413=$("${dc[@]}" exec -T api python -c '
import socket
s = socket.create_connection(("127.0.0.1", 8000), timeout=10)
s.sendall(b"POST /api/v1/records HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n"
          b"Content-Length: 65537\r\n\r\n")
got = b""
while chunk := s.recv(65536):
    got += chunk
print(got.partition(b"\r\n\r\n")[2].decode())') || fail "asking the API itself for its 413"
grep -qF API_BODY_TOO_LARGE <<<"$api_413" || fail "the API's own refusal of 64 KiB + 1 byte: $api_413"
for proto in --http1.1 --http2; do
  for _ in $(seq 1 20); do
    status=$(status_of "$proto" -H 'content-type: application/json' --data-binary "@$work/over64k.json" \
      "$base/api/v1/records")
    if [ "$status" != 413 ] || [ "$(cat "$work/answer")" != "$api_413" ]; then
      fail "64 KiB + 1 byte to /api/v1/records ($proto) answered $status: $(cat "$work/answer")"
    fi
  done
done
echo "64 KiB + 1 byte to /api/v1/records, 20 times over HTTP/1.1 and over HTTP/2 -> 413: $api_413"
# a chunked body must declare its length instead (411, any method; TASK-255), a PUT to /api/v1/compare included:
# with comparisons on, only a POST there is a file (TASK-268), and a PUT with a length gets the API's own 405
status=$(status_of --http1.1 -H 'Transfer-Encoding: chunked' -H 'content-type: application/json' \
  -d '{"q":"learning"}' "$base/api/v1/records")
echo "a chunked search record to /api/v1/records -> $status"
[ "$status" = 411 ] || fail "a chunked body to /api/v1/records answered $status"
status=$(status_of --http1.1 -X PUT -H 'Transfer-Encoding: chunked' -H 'content-type: application/x-research-info-systems' \
  --data-binary "@$work/over64k.json" "$base/api/v1/compare?q=$query")
echo "a chunked PUT to /api/v1/compare -> $status"
[ "$status" = 411 ] || fail "a chunked PUT to /api/v1/compare answered $status"
status=$(status_of -D "$work/headers" -X PUT -H 'content-type: application/x-research-info-systems' -d 'TY  - JOUR' \
  "$base/api/v1/compare?q=$query")
echo "a PUT with a length to /api/v1/compare -> $status: $(cat "$work/answer")"
if [ "$status" != 405 ] || ! grep -qF API_METHOD_NOT_ALLOWED "$work/answer" || ! grep -qi '^allow: POST' "$work/headers"; then
  fail "a PUT to /api/v1/compare didn't get the API's own 405 with Allow: POST ($status)"
fi
# an unsized HTTP/2 body (nothing in its headers says so) over the cap fails at it in the proxy: 413, the same
# words. One that stops at the cap and stays open waits inside the proxy's buffer, holding no API connection
status=$(status_of --http2 -X POST -T - -H 'content-type: application/json' "$base/api/v1/records" <"$work/over64k.json")
echo "an unsized HTTP/2 body of 64 KiB + 1 byte to /api/v1/records -> $status"
if [ "$status" != 413 ] || [ "$(cat "$work/answer")" != "$api_413" ]; then
  fail "an unsized HTTP/2 body over 64 KiB answered $status: $(cat "$work/answer")"
fi
head -c 65536 /dev/zero | tr '\0' x >"$work/cap64k.json"
# <service> <port>: its open connections from the proxy (a healthcheck connects from loopback)
proxied() {
  "${dc[@]}" exec -T "$1" cat /proc/net/tcp | python3 -c '
import socket, sys
peer = socket.inet_aton(sys.argv[1])[::-1].hex().upper()
port = ":%04X" % int(sys.argv[2])
rows = [line.split() for line in sys.stdin.read().splitlines()[1:]]
print(sum(1 for r in rows if r[1].endswith(port) and r[2].startswith(peer + ":") and r[3] == "01"))' "$OP_PROXY_ADDRESS" "$2"
}
# The web app takes no request body (no server actions, no route handlers): a page answers without reading
# one, and the web server lets go of the connection as it does after any request (its 5 s keep-alive), though
# the client is still sending and the proxy passes web bodies on unbuffered. So a body that stalls there holds
# nothing for read_body (measured; a route that read bodies would, and this would see it at 9 s)
sleep 6 # until the proxy's idle connections to the API and the web app are closed (each keeps one 5 s)
{
  cat "$work/cap64k.json"
  sleep 10
} | curl -sS --http2 -X POST -T - --cacert "$cert" -H 'content-type: application/json' -o /dev/null \
  "$base/api/v1/records" 2>/dev/null &
open_pid=$!
{
  printf 'q=learning'
  sleep 14
} | curl -sS --http1.1 -X POST -T - -H 'Transfer-Encoding: chunked' --cacert "$cert" -o /dev/null \
  -w '%{http_code}' "$base/search?q=$query" >"$work/web-stall" 2>/dev/null &
web_pid=$!
sleep 5
held=$(proxied api 8000) || fail "reading the API's connections"
sleep 4
web_held=$(proxied web 3000) || fail "reading the web app's connections"
wait "$open_pid" || true
wait "$web_pid" || true
echo "an unsized HTTP/2 body that stops at 64 KiB and stays open: API connections from the proxy after 5 s: $held"
[ "$held" = 0 ] || fail "an unsized body that stopped at the 64 KiB cap held $held API connection(s)"
echo "a chunked POST to /search that stalls: $(cat "$work/web-stall"); web connections from the proxy after 9 s: $web_held"
[ "$web_held" = 0 ] || fail "a stalled body to the web app held $web_held connection(s) to it"
# an error the proxy answers itself carries the site's headers too: HSTS, and no Server header. Its 413 on a
# web path, and its 502 while the web app is stopped
check_error_headers() { # <what> <expected status> <curl args…>
  local what=$1 want=$2 got
  shift 2
  got=$(curl -sS --cacert "$cert" -D "$work/headers" -o /dev/null -w '%{http_code}' "$@" || true)
  echo "$what -> $got; $(grep -ci '^strict-transport-security:' "$work/headers") HSTS, $(grep -ci '^server:' "$work/headers") Server header(s)"
  if [ "$got" != "$want" ] || ! grep -qi '^strict-transport-security: max-age=' "$work/headers" \
    || grep -qi '^server:' "$work/headers"; then
    fail "$what: not $want with HSTS and no Server header"
  fi
}
check_error_headers "64 KiB + 1 byte to /" 413 --data-binary "@$work/over64k.json" "$base/"
"${dc[@]}" stop web >/dev/null 2>&1 || fail "stopping web"
check_error_headers "GET / with web stopped" 502 "$base/"
"${dc[@]}" start web >/dev/null 2>&1 || fail "starting web"
for _ in $(seq 1 30); do
  [ "$(status_of "$base/")" = 200 ] && break
  sleep 1
done
[ "$(status_of "$base/")" = 200 ] || fail "the web app didn't come back after the 502 check"

step "7. no query text in any log"
"${dc[@]}" logs --no-color >"$work/logs.txt" 2>&1 || fail "reading the logs"
[ -s "$work/logs.txt" ] || fail "no logs to check"
if grep -qF -- "$query" "$work/logs.txt"; then
  fail "a log line holds the query text"
fi
echo "no log line holds the query ($(wc -l <"$work/logs.txt" | tr -d ' ') lines checked)"

printf '\nPASS\n'
