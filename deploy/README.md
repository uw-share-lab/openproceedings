# Deploying openproceedings

Docker Compose runs three services: `api` (`op serve`), `web` (the Next.js standalone server) and `caddy`
(TLS, the timeouts and body cap, and log filters that drop the query). Nothing here names a host or a provider:
that is TASK-064's decision. The requirements behind each setting are in
[spec 08](../docs/specs/08-ops-and-tooling.md) §Deploy and §Release. This file is the operator's runbook
(TASK-065). Every command runs from the repository root, as the operator's account, unless it says otherwise.

| File | What it is |
|---|---|
| `compose.yml` | the stack, plus two one-off services under the `ops` profile: `ops` (index retire) and `takedown-check` |
| `Caddyfile` | the proxy: site name from `OP_DOMAIN`, Caddy's local CA for `localhost`, ACME for a real name |
| `api.Dockerfile` | the `api` image: the backend package and its locked dependencies, user `op-api` (uid and gid 10001) |
| `web.Dockerfile`, `web-build-gate.sh` | the `web` image; a public build needs a takedown contact (decision-018, TASK-136) |
| `caddy.Dockerfile` | Caddy with the Caddyfile, as user `caddy` (uid 10002) |
| `index-permissions.sh` | gives `op-api` read access to one index version (§Permissions) |
| `smoke-test.sh` | the whole stack over a throwaway fixture (§Trying it locally) |

Every base image is pinned by digest (`make tooling` checks it, and Dependabot bumps it). Every container
has a read-only root filesystem, drops all capabilities and sets `no-new-privileges`. `api` and `web` sit on
an internal network with no route out, and only `caddy` publishes ports. Use **Docker Engine 26.0.0 or
later** (or 25.0.4 / 23.0.11): older engines forward DNS lookups out of an internal network
(CVE-2024-29018).

In the commands below, `dc` stands for `docker compose -f deploy/compose.yml`, and `$OP_API_UID` and
`$OP_API_GID` are the API's ids (§Permissions). Set all three in the operator's shell profile:
```bash
alias dc='docker compose -f deploy/compose.yml'
export OP_API_UID=10001 OP_API_GID=10001   # or your ids; keep deploy/.env the same
```
Compose reads `deploy/.env`, but the shell, `sudo` and the scripts here don't: the commands pass the ids
explicitly.

## Settings

Set these in the environment, or in `deploy/.env` (Compose reads a `.env` beside the compose file; it is
gitignored, like every `.env`).

| Variable | Default | Meaning |
|---|---|---|
| `OP_DATA_HOST` | required | the host's data directory (§The host's data directory) |
| `OP_INSTANCE` | required | `public` or `private`, the web image's build gate (decision-018) |
| `OP_TAKEDOWN_CONTACT` | empty | the takedown contact compiled into the web image; required when `public` |
| `OP_DOMAIN` | `localhost` | the site's name; `localhost` uses Caddy's local CA, a real name uses Let's Encrypt (DNS must point here, and ports 80 and 443 must be reachable) |
| `OP_HSTS` | `max-age=63072000` | the `Strict-Transport-Security` value. Leave `includeSubDomains` out until TASK-064 decides the domain (`Caddyfile`) |
| `OP_HTTP_PORT`, `OP_HTTPS_PORT` | `80`, `443` | the host ports |
| `OP_TAKEDOWN_LOG_HOST` | none | the directory that holds the takedown log, used only by `takedown-check` |
| `OP_API_UID`, `OP_API_GID` | `10001`, `10001` | the `api` user's uid and gid, built into the image; ids no host account or group uses (§Permissions) |
| `OP_IMAGE_TAG` | `local` | the tag of the images compose builds (`smoke-test.sh` uses its own, so it never replaces these) |
| `OP_INTERNAL_SUBNET`, `OP_INTERNAL_IP_RANGE`, `OP_PROXY_ADDRESS` | `172.30.80.0/24`, `172.30.80.128/25`, `172.30.80.2` | the internal network, the part of it `api` and `web` get addresses from, and Caddy's fixed address outside that part: the one address `op serve --trusted-proxy` believes `X-Forwarded-For` from. Change them only if the subnet clashes with the host's |

## The host's data directory

```
$OP_DATA_HOST/
├── indexes/      current -> <index_version>, and one directory per version   (read-write mount, closed by modes: §Permissions)
├── snapshots/    the snapshot of every index kept                            (read-only)
├── records/      records.sqlite: every saved search                          (read-write; 0700, $OP_API_UID)
└── takedowns/    withheld.txt and nothing else                               (read-only)
```

- **`takedowns/` holds only `withheld.txt`.** The `api` container mounts the directory, never the file alone,
  because an editor that saves by renaming would otherwise leave the container reading the old list after a
  SIGHUP. It must never contain the log. Keep the takedown log (decision-022 and its 2026-10-02 addendum) in
  its own directory outside the data directory, for example `/srv/openproceedings/takedown-log/log.jsonl`,
  with the directory 0700 and the file 0600, both owned by the operator's account (the owner's requirements: a
  host file outside the repository that only the operator can read). Set it up once, as the operator:
  ```bash
  install -d -m 0700 /srv/openproceedings/takedown-log
  (umask 077 && touch /srv/openproceedings/takedown-log/log.jsonl)   # 0600
  ```
  Name the directory with `OP_TAKEDOWN_LOG_HOST`. On a fresh instance `withheld.txt` is an empty file. It must
  exist, because `op serve` behind the proxy refuses to load without it (`takedowns_missing`). Give it mode 0644
  and the directory 0755.
- **`records/` is the only copy of every saved search.** It belongs to `op-api`. Create it once with
  `sudo install -d -o "$OP_API_UID" -g "$OP_API_GID" -m 0700 "$OP_DATA_HOST/records"`. Compose refuses to
  start without it, rather than create one the API can't write. Read or write records only as that user,
  through the `api` container (`dc exec api op record replay <id> --json`): a store written by another user
  is one the API can't open. Because the operator can't read it, an `op index retire` run on the host refuses
  (`records_unreadable`) instead of counting no pins; run retire only in the `ops` container
  (§Retiring an index). Back it up (§Backups).
- **Snapshots stay** while any kept index was built from them: there is no snapshot retire command, and a
  pinned index's exports need its snapshot to attribute each abstract (decision-021).
- `cache/` (the crawl cache) is not mounted. Build snapshots and indexes on the host from a checkout of the
  release the images run, as the operator (§Promoting an index).

## Permissions

`api` runs as `op-api` (uid and gid 10001 by default), which is neither root nor the operator's account that
owns the log (TASK-065 AC #3). File modes on the host see only the numbers, so **no host account or group may
already have them**: one that did could read the record store and open the indexes. Check once on the host:
```bash
getent passwd 10001; getent group 10001   # nothing, or a reserved nologin system account for the API
```
If either belongs to a person (the operator included) or another service, pick free ids, set `OP_API_UID` and
`OP_API_GID` both in `deploy/.env` (for compose) and in the shell (for the commands below), and rebuild
(`dc build`).

Tantivy can't open an index without writing its lock file, `.tantivy-meta.lock`, so the `indexes/` mount
can't be read-only. Plain file modes keep the API from changing the index instead:

- `indexes/` itself: owned by the operator, mode 0755. The API can't add, remove or repoint anything there.
- each version directory: group `op-api` (`$OP_API_GID`), mode 0750. Its files stay 0444, as the build left
  them, and only its two `.tantivy-*.lock` files are group-writable (0660).

`op index build` leaves a new version directory 0700 and owned by the operator. Before serving it, run
`sudo deploy/index-permissions.sh "$OP_DATA_HOST/indexes" <index_version> "$OP_API_GID"`, or run it as an
account in the host group with that gid. The gid is a required argument, never a default. The script refuses a
version directory that holds a symlink. Snapshots and the takedown list are readable as built: the snapshot
files are 0444 in 0555 directories. `smoke-test.sh` checks all of this on a Linux host: `op-api` can open the
index and can't create, delete or rename anything in it.

## First start

1. Put the data in place: an index and its snapshot, `indexes/current` pointing at it (a relative link, a
   bare `<index_version>`: an absolute host path doesn't resolve inside the containers), `records/` (above)
   and `takedowns/withheld.txt`. Run `deploy/index-permissions.sh` for the version.
2. With the settings in place (`OP_DATA_HOST`, `OP_INSTANCE`, and for a public instance `OP_DOMAIN`,
   `OP_TAKEDOWN_CONTACT`):
   ```bash
   dc up -d --build --wait
   ```
3. Check over TLS. On a real domain:
   ```bash
   curl -sS https://<OP_DOMAIN>/api/v1/healthz   # {"index_loaded":true,"index_version":"<v>",…}
   ```
   On `localhost`, trust Caddy's local CA for that one request:
   ```bash
   dc cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
   curl -sS --cacert caddy-root.crt https://localhost/api/v1/healthz
   ```
   The first load re-hashes every index file, and `/healthz` reports `"index_loaded": false` until it is
   done. The healthcheck gives it 120 s.
4. Check that Caddy sees real client addresses: its access log's `client_ip` must be each client's own, IPv6
   clients included. The API's rate limit is keyed on it; one shared address would put every client in one
   bucket. Docker's userland proxy hands IPv6 clients to Caddy as the bridge's gateway when the `edge` network
   has no IPv6 (turn on `enable_ipv6` there, or set `"userland-proxy": false` in the daemon), and a provider's
   load balancer in front needs Caddy's `trusted_proxies` naming its range.
5. On a public instance, also run `takedown-check` (§Takedowns), and check the rate limit and CORS on the
   live instance (TASK-067 AC #2). Compose passes no `--cors-origin` (the web app is on the API's origin), so a
   foreign `Origin` gets no `access-control-allow-origin`.

The API's Swagger UI is off, because `op serve` turns it on only on loopback. Logs are JSON on each
container's stdout (`dc logs`). No log line holds a query: the API never logs one, and Caddy deletes the URI
and the Referer from its access and error logs.

**Never run `dc down -v`.** It deletes the `caddy-data` volume (the ACME account, the certificates and the
local CA). `dc down` without `-v` keeps it. The record store is a host directory and survives either way, but
back it up before any change to the host (§Backups).

## Deploying a release

Code and data ship separately (spec 08 §Release): a code release never changes which `index_version` is
served, and promoting an index is its own procedure (next section).

1. `git fetch --tags && git checkout vX.Y.Z`, then `dc up -d --build --wait`. Compose rebuilds the images
   from that checkout and replaces the containers. The API reloads `current`.
2. Confirm `/api/v1/healthz` and `/api/v1/meta` (the same `index_version` as before) over TLS.
3. **A release that changes `TOKENIZER_VERSION`, `SCHEMA_VERSION` or Tantivy** can't serve an index built by
   older code (`unservable`). Build and verify the new index first, with that release's checkout
   (§Promoting an index, steps 1 to 3, run on the host from the release's checkout). Then build the images
   first (`dc build`, which takes minutes), switch `current` to the new index as in §Promoting an index,
   step 4 (without the SIGHUP), and start the new code at once with `dc up -d --wait`. Building first keeps
   the old code from ever running against an index it can't serve. Keep the older indexes that records pin: the
   release each was saved under still serves them (spec 08 §Release, step 8).
4. **Rollback:** check out the previous tag and `dc up -d --build --wait`. If the release also changed
   `current`, point it back first.

Build snapshots and indexes on the host from the same checkout the images run, or the API may refuse the
index.

## Promoting an index

1. **Build**, on the host, as the operator, with `export OP_DATA_DIR=$OP_DATA_HOST`:
   `uv run op snapshot build` (read its `takedowns_followed` and `takedowns_unmatched`: step 6), then
   `uv run op snapshot diff <old snapshot> <new snapshot>` and read the diff, then
   `uv run op index build --snapshot <new snapshot>`.
2. **Verify** on the new version, with the code the images run (spec 08 §Release, step 3):
   - `uv run pytest backend/tests/golden backend/tests/contract`;
   - `uv run op index parity --index <new_version>`;
   - `uv run op eval coverage --index <new_version> --check --out "$(mktemp -d)"` (the M4 gate; no report
     lands in the tree).
   For a release that changes `TOKENIZER_VERSION`, `SCHEMA_VERSION` or Tantivy, run all of these from the
   release's checkout on the host: the running images can't serve the new index.
3. **Permissions:** `sudo deploy/index-permissions.sh "$OP_DATA_HOST/indexes" <new_version> "$OP_API_GID"`.
   Then replay a sample of saved searches on the API's own store, `dc exec api op record replay <id> --json`. This
   checks the running code, not the new index: a record replays on its own index whenever that index is kept, so
   every sampled record whose index is kept must report `reproduced`, and `mismatch` (exit 3) blocks the
   promotion. `--index <new_version>` applies only to a record whose own index is gone.
4. **Switch `current` atomically and reload:**
   ```bash
   cd "$OP_DATA_HOST/indexes" && ln -sfn <new_version> current.tmp && mv -T current.tmp current && cd -
   dc kill -s HUP api
   ```
   The link is relative (a bare version name). `mv -T` (GNU) renames over the old link in one step. The
   `init` process forwards SIGHUP to `op serve`, which loads the new version in the background and serves the
   old one until the new one is ready.
5. **Confirm:** `/api/v1/meta` and `/api/v1/healthz` report `<new_version>`. The API's log has
   `index_swapped`, or `index_load_failed` with the old version kept.
6. **Takedowns,** while the list names anything: for each id in `takedowns_followed` (a listed paper the
   build holds under a new id), add the new id to `withheld.txt`, log a `withheld` entry for it (the same
   requester and basis), **keep the old id**, and SIGHUP. Keep every id in `takedowns_unmatched` listed while
   any loaded version holds it. Then run `takedown-check` (§Takedowns), and fill in `first_index_version` in
   the log for the requests this version is the first to withhold.
7. **Rollback:** point `current` back at the old version (step 4) and SIGHUP. Keep the old version until
   the new one has been served for a while.

## Retiring an index

`op index retire` (TASK-085) deletes a version that no search record pins and that nothing serves. Run it
only in the `ops` container, which has the record store and write access to `indexes/`. On the host it
refuses, since the operator can't read the store.

1. Confirm the new version is served (§Promoting an index, step 5), and that no other instance serves the
   old one by name (`op serve --index <v>`): retire can't see that.
2. `grep -rn <old_version> docs/results "$OP_DATA_HOST/embeddings"` (from a checkout): a version a committed report
   cites is a decision to retire, not a default.
3. Retire:
   ```bash
   dc run --rm ops index retire <old_version> --dry-run   # the checks only
   dc run --rm ops index retire <old_version>
   ```

It refuses, deleting nothing, when `current` or any other symlink in `indexes/` points at the version, when
a search record pins it, or when the record store can't be read. If it logs ERROR
`index_retire_restore_failed`, move the directory back by hand,
`sudo mv "$OP_DATA_HOST/indexes/.retiring-<v>" "$OP_DATA_HOST/indexes/<v>"`, before serving, building or
retiring again. The `ops` container runs as root and keeps `CAP_CHOWN`: SQLite then gives any `-shm` or `-wal`
file it creates in the store to `op-api`, the database's owner. Without that capability those files stay
root's, and the API's next save fails. `smoke-test.sh` checks the store's owners after a retire.

## Takedowns

The procedure is spec 08 §Deploy ("Takedown procedure"; decision-022). In this deployment the log lives
outside the data directory, at `$OP_TAKEDOWN_LOG_HOST/log.jsonl`.

1. **Log** the request in the log (one JSON object: `record_id`, `received`, `requester`, `basis`,
   `decision`, `applied`, `first_index_version`).
2. **Withhold:** add the id to `$OP_DATA_HOST/takedowns/withheld.txt`, then `dc kill -s HUP api`. Every
   loaded version withholds the abstract from that reload on. Look for `takedowns_reloaded` in the API's log,
   then set the entry's `applied` date.
3. **Check**, as the operator's account, against the API itself (on the internal network, not through the
   proxy):
   ```bash
   dc run --rm --user "$(id -u):$(id -g)" takedown-check
   ```
   It exits 0 when no loaded version serves a listed abstract and the log agrees with the list.
4. **Rebuild and promote** (§Promoting an index): the new snapshot no longer holds the abstract. Set the
   entry's `first_index_version` to the version just promoted.
5. **Check again** (step 3), and after every promotion while the list names anything.

**Lifting a takedown:** append a `lifted` entry (with its `applied` date), remove the line from
`withheld.txt`, and SIGHUP. Versions that still hold the text show it again. A snapshot built while the id
was listed keeps it withheld until a rebuild without the id is promoted.

## Comparisons with a reviewer's own RIS file (off by default)

`POST /api/v1/compare` and the search page's "Compare with your records" (spec 04 §Comparing with a RIS file)
are off on this stack: `op serve` behind a proxy doesn't offer them unless told to. Turning them on is your
decision as the operator (decision-035), and not before the proxy block below has been fixed and has passed
`smoke-test.sh` on your stack (TASK-183): it is what keeps a slow upload off the API's one comparison slot, and
**as written it cannot work** (see the note under it). What it means:

- anyone can upload a RIS file of up to 16 MiB and 5,000 records. It is read in memory for that one request
  and dropped: never written to disk, never logged (the access line has counts only), never added to the
  index. One comparison runs at a time (another is told to retry before its file is read), so the `api`
  process holds at most one file: budget about 250 MB (about 238 MiB) per comparison slot there (one 16 MiB file raised the
  process's resident memory by 142 MiB at its peak in the security review: the file, its text, its parsed
  records and the answer; a file of the same size with a 4-byte character on each long line peaked near
  210 MiB before matching in the release security review of 2026-10-05 (a traced 192 MiB to decode and
  parse it, plus the 16 MiB body), since Python then stores its text at 4 bytes a character, so size from the 250 MB,
  never from either measurement). The proxy is another matter: it buffers **every** upload in flight before the API
  can refuse it (`request_buffers`), up to 16 MiB each, with no limit on how many arrive at once (200
  concurrent uploads ≈ 3.2 GB, and they cost no tokens). Budget 16 MiB per concurrent upload in the proxy, and
  give the `caddy` service a memory limit (`mem_limit` in `compose.yml`, which sets none today) as part of
  turning comparisons on;
- each comparison is up to a minute of CPU in the `api` process (about 10 s per 1,000 records: the reference
  matcher decides why each paper was dropped), during which searches are slower. Its client pays for the
  time from its rate-limit bucket;
- the served index's match table takes about 80 MB more memory (95,877 records), built in the background
  after each load (`match_index_built` in the log).

They are off here because `compose.yml` passes `--trusted-proxy`. If you run `op serve` yourself on 127.0.0.1
behind a proxy on the same host, pass `--trusted-proxy <the proxy's address>` (or `--no-compare`): without
either, the API takes a loopback bind for a local instance. It then refuses a comparison to every request the
proxy forwards (one carrying `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Real-IP`,
`Forwarded`, `Via` or `CF-Connecting-IP`) and to every page not on that machine (a non-loopback `Origin`), and
`GET /api/v1/meta` doesn't offer comparisons to those requests; a proxy that sets none of those headers, in
front of a client that sends no `Origin`, would still offer comparisons to everyone it serves.

A network (IPv4 /24, IPv6 /48) runs one comparison at a time and then waits three times as long as its
comparison held the slot, so one network holds the slot at most a quarter of the time; many networks together
can still fill it, and comparisons are then refused while searches are not.

To turn them on: add `--compare` to the `api` service's `command` in `compose.yml`, and let that one path
through the proxy with a larger body (everything else keeps 64KB), by adding to the `Caddyfile`'s
site block, before the general `reverse_proxy /api/*`:

```
	@compare path /api/v1/compare
	handle @compare {
		request_body {
			max_size 16MB
		}
		reverse_proxy api:8000 {
			request_buffers 16MB # the whole file is read here before the API sees the request
		}
	}
```

**This block cannot work as written** (TASK-183 fixes it and runs it through `smoke-test.sh`): the site-wide
`request_body { max_size 64KB }` (`Caddyfile`) wraps it first, so a file over 64 KB is refused before this
block is reached (the 64 KB cap must be scoped to `@rest not path /api/v1/compare` instead); and Caddy's `16MB`
is 16,000,000 bytes, under the 16,777,216 (16 MiB) the API advertises in `limits.compare`, so write `16MiB`.
Check the edited file with `caddy validate` before reloading, and raise the server's `read_body` timeout to
what a 16 MiB upload needs on your users' links (`read_body 60s` admits 2 Mbit/s). `read_body` is a timeout of
the whole server, every path, not of this one: Caddy has no per-path setting for it. With `--compare` the network pause above applies (an instance on by the loopback default has none).
`GET /api/v1/meta` then shows `limits.compare`, and the web app offers the panel; no rebuild
of the `web` image is needed. To turn them off again, remove `--compare` and restart `api`.

## Backups

`$OP_DATA_HOST/records/records.sqlite` holds the only copy of every saved search. Losing it also unpins
every index, so they could be retired. Make a consistent copy through SQLite's backup API, as `op-api`,
streamed out of the container:

```bash
(umask 077; dc exec -T api python -c "
import sqlite3, sys, tempfile
with tempfile.NamedTemporaryFile(dir='/tmp') as f:
    sqlite3.connect('/data/records/records.sqlite').backup(sqlite3.connect(f.name))
    sys.stdout.buffer.write(open(f.name, 'rb').read())
" > records-backup-$(date +%F).sqlite)   # umask 077: the file is 0600
```

The temporary copy is deleted inside the container. Keep the backups somewhere only the operator can read:
they hold every saved query. Back up the snapshots and indexes that records pin, too. They are immutable, so
a copy taken once is enough.

## Trying it locally

`deploy/smoke-test.sh` builds the images under its own tag and starts the stack over a fixture data
directory in a temporary directory. It uses its own Compose project, `openproceedings-smoke`, so it never
touches a running stack or its images. It checks what this runbook claims:

- healthz and the web root over https://localhost;
- the API's user, its read-only mounts, and a takedown directory holding only `withheld.txt`;
- a promotion;
- retires: refused for the served version and for a pinned one, refused on the host, and done for an
  unpinned one, with the record store still the API's and a backup that opens;
- a withheld abstract next to a served one, with `takedown-check` passing;
- no query text in any log.

It removes everything it created on exit. It needs Docker and uv, and ports 80 and 443 (or
`OP_HTTP_PORT`/`OP_HTTPS_PORT`). Docker Desktop keeps a host file's owner on bind mounts, so there the
ownership steps and checks (§Permissions, and the host-side retire) are skipped and say so. They run on a
Linux host. No CI job runs it.

## What remains for a real host (TASK-064, then TASK-065)

- Choose the host and the domain (TASK-064). Point DNS at the host, and open ports 80 and 443.
- Install Docker Engine 26.0.0 or later.
- Set `OP_DOMAIN`, `OP_INSTANCE=public`, `OP_TAKEDOWN_CONTACT` and `OP_TAKEDOWN_LOG_HOST`. Once the domain is
  known, decide about `includeSubDomains` in `OP_HSTS`.
- Set up the host's accounts: the operator's account, and sudo (or a host group with `$OP_API_GID`) for
  `index-permissions.sh` and `records/`. Check that uid and gid 10001 are unused on the host, or a reserved
  nologin account for the API; if not, set `OP_API_UID`/`OP_API_GID` in `deploy/.env` and the shell, and
  rebuild (§Permissions).
- Do the first start and its checks on the host: client addresses (First start, step 4), and the rate limit
  and CORS (TASK-067 AC #2).
- Schedule the record-store backup (§Backups).
