# Deploying openproceedings

Docker Compose runs three services: `api` (`op serve`), `web` (the Next.js standalone server) and `caddy`
(TLS, the timeouts and body cap, and log filters that drop the query). Nothing here names a host or a provider:
that is TASK-064's decision. The requirements behind each setting are in
[spec 08](../docs/specs/08-ops-and-tooling.md) §Deploy.
This file is the operator's runbook (TASK-065).

| File | What it is |
|---|---|
| `compose.yml` | the stack, plus two one-off services under the `ops` profile: `ops` (index retire) and `takedown-check` |
| `Caddyfile` | the proxy: site name from `OP_DOMAIN`, Caddy's local CA for `localhost`, ACME for a real name |
| `api.Dockerfile` | the `api` image: the backend package and its locked dependencies, user `op-api` (uid and gid 10001) |
| `web.Dockerfile`, `web-build-gate.sh` | the `web` image; a public build needs a takedown contact (decision-018) |
| `caddy.Dockerfile` | Caddy with the Caddyfile, as user `caddy` (uid 10002) |
| `index-permissions.sh` | gives `op-api` read access to one index version (§Permissions) |
| `smoke-test.sh` | the whole stack over a throwaway fixture: TLS, users and mounts, promotion, retire, a takedown, logs |

Every base image is pinned by digest (`make tooling` checks it, and Dependabot bumps it). Every container
has a read-only root filesystem, drops all capabilities and sets `no-new-privileges`. `api` and `web` sit on
an internal network that has no route out, and only `caddy` publishes ports.

## Settings

Set these in the environment, or in `deploy/.env` (Compose reads a `.env` beside the compose file; it is
gitignored, like every `.env`).

| Variable | Default | Meaning |
|---|---|---|
| `OP_DATA_HOST` | required | the host's data directory: `indexes/` (with `current`), `snapshots/`, `takedowns/` |
| `OP_INSTANCE` | required | `public` or `private`, the web image's build gate (decision-018) |
| `OP_TAKEDOWN_CONTACT` | empty | the takedown contact compiled into the web image; required when `public` |
| `OP_DOMAIN` | `localhost` | the site's name; `localhost` uses Caddy's local CA, a real name uses Let's Encrypt (DNS must point here, and ports 80 and 443 must be reachable) |
| `OP_HSTS` | `max-age=63072000` | the `Strict-Transport-Security` value. Leave `includeSubDomains` out until TASK-064 decides the domain (`Caddyfile`) |
| `OP_HTTP_PORT`, `OP_HTTPS_PORT` | `80`, `443` | the host ports |
| `OP_TAKEDOWN_LOG_HOST` | none | the directory that holds the takedown log, used only by `takedown-check` |
| `OP_INTERNAL_SUBNET`, `OP_INTERNAL_IP_RANGE`, `OP_PROXY_ADDRESS` | `172.30.80.0/24`, `172.30.80.128/25`, `172.30.80.2` | the internal network, and Caddy's fixed address on it, which is the one address `op serve --trusted-proxy` believes `X-Forwarded-For` from. Change them only if the subnet clashes with the host's |

## The host's data directory

```
$OP_DATA_HOST/
├── indexes/      current -> <index_version>, and one directory per version   (mounted read-write; see §Permissions)
├── snapshots/    the snapshot of every index kept                            (read-only)
└── takedowns/    withheld.txt and nothing else                               (read-only)
```

- **`takedowns/` holds only `withheld.txt`.** The `api` container mounts the directory, never the file alone,
  because an editor that saves by renaming would otherwise leave the container reading the old list after a
  SIGHUP. It must never contain the log. Keep the takedown log (decision-022) in its own directory outside
  the data directory, for example `/srv/openproceedings/takedown-log/log.jsonl`, with the directory 0700 and
  the file 0600, both owned by the operator's account. Name it with `OP_TAKEDOWN_LOG_HOST`. On a fresh
  instance `withheld.txt` is an empty file. It must exist, because `op serve` behind the proxy refuses to load
  without it (`takedowns_missing`). Give it mode 0644 and the directory 0755.
- **Search records** live in the `records` volume, which belongs to `op-api` (0700, and 0600 for the database).
  Read or write them only as that user, through the `api` container: `docker compose exec api op record replay
  <id>`. A store written by another user is one the API can't open (spec 08 §Deploy).
- `cache/` (the crawl cache) is not mounted. Build snapshots and indexes on the host from a checkout, as the
  operator (§Promoting an index).

## Permissions

Run `api` as `op-api` (uid 10001), which is neither root nor the operator's account that owns the log
(TASK-065 AC #3). Tantivy can't open an index without writing its lock file, `.tantivy-meta.lock`, so the
`indexes/` mount can't be read-only. Plain file modes keep the API from changing the index instead:

- `indexes/` itself: owned by the operator, mode 0755. The API can't add, remove or repoint anything there.
- each version directory: group `op-api` (gid 10001), mode 0750. Its files stay 0444, as the build left
  them, and only its two `.tantivy-*.lock` files are group-writable (0660).

`op index build` leaves a new version directory 0700 and owned by the operator. Before serving it, run
`deploy/index-permissions.sh $OP_DATA_HOST/indexes <index_version>` as root, or as an account in a host group
with gid 10001. This was checked on a Linux volume: `op-api` can open the index and can't create, delete or
rename anything in it. `smoke-test.sh` checks the same on a Linux host. Snapshots and the takedown list are
readable as built: the snapshot files are 0444 in 0555 directories.

## First start

1. Put the data in place: an index and its snapshot, `indexes/current` pointing at it, and
   `takedowns/withheld.txt` (empty is fine). Then run `deploy/index-permissions.sh` for the version.
2. From the repository root:
   ```bash
   docker compose -f deploy/compose.yml up -d --build --wait
   ```
3. Check over TLS. On a real domain:
   ```bash
   curl -sS https://<OP_DOMAIN>/api/v1/healthz   # {"index_loaded":true,"index_version":"<v>",…}
   ```
   On `localhost`, trust Caddy's local CA for that one request:
   ```bash
   docker compose -f deploy/compose.yml cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
   curl -sS --cacert caddy-root.crt https://localhost/api/v1/healthz
   ```
   The first load re-hashes every index file, and `/healthz` reports `"index_loaded": false` until it is
   done. The healthcheck gives it 120 s.
4. On a public instance, also run `op takedown check` (§Takedowns), and check the rate limit and CORS on the
   live instance (TASK-067 AC #2).

The API's Swagger UI is off, because `op serve` turns it on only on loopback. Logs are JSON on each
container's stdout (`docker compose logs`). No log line holds a query: the API never logs one, and Caddy
deletes the URI and the Referer from its access and error logs.

## Promoting an index

Code and data ship separately (spec 08 §Release): promoting an index is this procedure, run on its own.

1. **Build**, on the host from a checkout, as the operator, with `OP_DATA_DIR=$OP_DATA_HOST`:
   `uv run op snapshot build`, then `uv run op snapshot diff <old snapshot> <new snapshot>` and read the diff, then
   `uv run op index build --snapshot <new snapshot>`, then `uv run op index parity --index <new_version>`.
   The build applies `takedowns/withheld.txt`. Report what it says about `takedowns_followed` and
   `takedowns_unmatched` in the takedown log (spec 08 §Deploy, step 3).
2. **Permissions:** `deploy/index-permissions.sh $OP_DATA_HOST/indexes <new_version>`.
3. **Switch `current` and reload:**
   ```bash
   ln -sfn <new_version> "$OP_DATA_HOST/indexes/current"
   docker compose -f deploy/compose.yml kill -s HUP api
   ```
   The `init` process forwards SIGHUP to `op serve`. The API loads the new version in the background and keeps
   serving the old one until the new one is ready.
4. **Confirm:** `/api/v1/meta` reports `<new_version>` (`curl -sS https://<OP_DOMAIN>/api/v1/meta`). The log has
   `index_swapped`, or `index_load_failed` with the old version kept.
5. **Takedowns:** if the list names anything, run `op takedown check` (§Takedowns) and record
   `first_index_version` in the log.
6. **Rollback:** point `current` back at the old version and send SIGHUP again. Keep the old version until
   the new one has been served for a while.

## Retiring an index

`op index retire` (TASK-085) deletes a version that no search record pins and that nothing serves. It runs
in the `ops` container, which has the record store and write access to `indexes/`:

```bash
docker compose -f deploy/compose.yml run --rm ops index retire <old_version> --dry-run   # the checks only
docker compose -f deploy/compose.yml run --rm ops index retire <old_version>
```

The command refuses, deleting nothing, when `current` points at the version, when a search record pins it,
or when the record store can't be read. It can't see an instance that serves the version by name, so run it
only after step 4 above has confirmed the new version. The `ops` container runs as root and keeps
`CAP_CHOWN`: SQLite then gives any `-shm` or `-wal` file it creates in the store to `op-api`, the database's
owner. Without that capability those files stay root's, and the API's next save fails. `smoke-test.sh`
checks the store's owners after a retire.

## Takedowns

The procedure is spec 08 §Deploy ("Takedown procedure"), with the log kept outside the data directory as
described above. In this deployment:

- **Withhold:** append the id to `$OP_DATA_HOST/takedowns/withheld.txt`, log the request, then
  `docker compose -f deploy/compose.yml kill -s HUP api`. Look for `takedowns_reloaded` in the API's log.
- **Check**, as the operator's account, against the API itself (on the internal network, not through the
  proxy):
  ```bash
  OP_TAKEDOWN_LOG_HOST=/srv/openproceedings/takedown-log \
    docker compose -f deploy/compose.yml run --rm --user "$(id -u):$(id -g)" takedown-check
  ```
  It exits 0 when no loaded version serves a listed abstract and the log agrees with the list. Run it after
  every promotion while the list names anything.

## Trying it locally

`deploy/smoke-test.sh` builds the images and starts the stack over a fixture data directory in a temporary
directory. It uses its own Compose project, `openproceedings-smoke`, so it never touches a running stack.
It checks everything this runbook claims: healthz and the web root over https://localhost, the API's user
and read-only mounts, a promotion, refused and successful retires, a withheld abstract with `op takedown
check` passing, and no query text in any log. It cleans up after itself. It needs Docker and uv, and ports
80 and 443 (or `OP_HTTP_PORT`/`OP_HTTPS_PORT`). Docker Desktop keeps a host file's owner on bind mounts, so
there the ownership checks (§Permissions) are skipped and say so. They run on a Linux host.

## What remains for a real host (TASK-064, then TASK-065)

- Choose the host and the domain (TASK-064). Point DNS at the host, and open ports 80 and 443.
- Set `OP_DOMAIN`, `OP_INSTANCE=public`, `OP_TAKEDOWN_CONTACT` and `OP_TAKEDOWN_LOG_HOST`. Once the domain is
  known, decide about `includeSubDomains` in `OP_HSTS`.
- Set up the host's accounts: the operator's account, and a host group with gid 10001 for
  `index-permissions.sh`, or run it with sudo.
- Do the first start and the checks above on the host, including the rate limit and CORS (TASK-067 AC #2).
- Back up the `records` volume, which holds the only copy of every saved search. Make a consistent copy
  through SQLite's backup API, as `op-api`:
  `docker compose exec -T api python -c "import sqlite3; sqlite3.connect('/data/records/records.sqlite').backup(sqlite3.connect('/tmp/records-backup.sqlite'))"`,
  then `docker compose cp api:/tmp/records-backup.sqlite <backup dir>/`.
