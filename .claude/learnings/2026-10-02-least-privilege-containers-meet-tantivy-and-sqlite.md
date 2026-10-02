# Least-privilege containers break on Tantivy's reader lock and on SQLite run as root without CAP_CHOWN

**Key lesson:** Before hardening a container, run the real program under the hardened settings. Tantivy can't open an index from a `:ro` mount (its reader takes `.tantivy-meta.lock` for writing), and SQLite run as root with every capability dropped leaves root-owned `-shm`/`-wal` files that lock the service's own user out of its store. Both were found only by running the stack.

- **Date:** 2026-10-02 · **Task:** task-065 · **Area:** ops
- **Artifacts:** `deploy/compose.yml`, `deploy/api.Dockerfile`, `deploy/caddy.Dockerfile`, `deploy/Caddyfile`,
  `deploy/index-permissions.sh`, `deploy/smoke-test.sh`, `deploy/README.md`,
  `backend/tests/deploy/fixture_data.py`

## What we set out to do
Build the compose deployment (api, web and Caddy over TLS), with the api container running as neither root nor
the operator's account and mounting the takedown list read-only. Then prove it locally.

## What we learned
- **Tantivy needs a write.** With `indexes/` mounted `:ro`, the load failed in `open_index` (`index_load_failed`,
  `ValueError`). Group modes give the API exactly what it needs: the version directory 0750 with group op-api,
  the files 0444, and only the two `.tantivy-*.lock` files 0660. Checked on a Linux volume: the API opens the
  index, and `touch`, `rm` and `ln -sfn current` in `indexes/` are all refused.
- **SQLite needs the -shm, and as root it chowns.** `op index retire` reads the record store with `mode=ro`.
  On a read-only mount that fails ("unable to open database file") because SQLite must open `-shm` for writing.
  On a read-write mount as root with `cap_drop: ALL`, SQLite's `fchown` of the new `-shm`/`-wal` to the
  database's owner fails silently. The files stay root's 0600, and the API's next `POST /records` was a 500.
  With `CAP_CHOWN` kept, they come out owned by op-api. The smoke test asserts the owners after every retire.
- **File capabilities and `cap_drop: ALL` don't mix.** The caddy image ships `/usr/bin/caddy` with
  `cap_net_bind_service=ep`. With every capability dropped, `exec` fails with EPERM, because the kernel won't
  run a binary whose file capability it can't grant. `setcap -r` in the image, plus the namespaced sysctl
  `net.ipv4.ip_unprivileged_port_start=0`, let a non-root Caddy bind 80 and 443.
- **A static proxy address needs an `ip_range`.** Docker handed `web` the address reserved for Caddy (the
  next free one), so Caddy's start failed with "Address already in use". `ip_range` keeps api and web in the
  upper half of the subnet.
- **Docker Desktop hides ownership.** Its file sharing keeps the host's owner and modes on bind mounts, so
  `chgrp` from a container is refused, and a uid mismatch doesn't block a write either. The ownership checks
  run only on Linux: the smoke test was run once in privileged ubuntu docker-in-docker, with
  `/var/lib/docker` on a volume, because nested overlayfs fails a BuildKit build with `invalid argument`.
- **`uv run` from `backend/` doesn't install the root's dev group.** In a clean checkout,
  `cd backend && uv run python -m tests…` had no pytest. Run from the root with `PYTHONPATH=backend`, as
  Playwright's fixture server does.
