---
id: TASK-065
title: 'Deploy: compose, Caddy TLS, index promotion runbook'
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-10-02 19:33'
labels:
  - ops
milestone: m-6
dependencies:
  - TASK-064
  - TASK-046
ordinal: 64000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 08 §Deploy (release-manager).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 docker compose up serves api + web over TLS
- [x] #2 Index promotion documented and tested; the runbook covers retire (implemented in TASK-085)
- [x] #3 The api container mounts, read-only, a directory that holds only `withheld.txt` (an empty file on a fresh instance: `op serve` off loopback, or behind a trusted proxy, refuses to load without it; TASK-067), never `log.jsonl`, and not the file alone (an editor that saves by rename would leave the container reading the old list across SIGHUP); it runs neither as root nor as the operator account that owns the log (source: TASK-136 deferral and TASK-067 review; spec 08 §Deploy, the takedown-log bullet)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Host-agnostic: nothing names a host (TASK-064 decides).
1. deploy/api.Dockerfile (uv, locked, no dev; user op-api 10001), deploy/caddy.Dockerfile (unprivileged, file capability removed), deploy/Caddyfile (spec 08 directives; OP_DOMAIN with local CA for localhost, ACME otherwise; OP_HSTS without includeSubDomains by default), deploy/compose.yml (api, web, caddy; ops and takedown-check one-offs; internal network; read-only root fs, cap_drop ALL, no-new-privileges).
2. Mounts (AC#3): takedowns/ read-only holding only withheld.txt; indexes/ closed by modes (deploy/index-permissions.sh), since Tantivy needs the lock file; records in a named volume owned by op-api.
3. Runbook deploy/README.md: settings, first start, promotion, retire, takedowns, what remains for the host (AC#2).
4. deploy/smoke-test.sh over a fixture (backend/tests/deploy/fixture_data.py): TLS, users and mounts, promotion, retire, takedown, logs. Run it on Docker Desktop and on Linux (docker-in-docker).
5. Spec 08 §Deploy, decision-022 addendum (log location under compose), CLAUDE.md as-built.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From the task-023 review (2026-09-26): a Tantivy index directory must be writable to open (readers take .tantivy-meta.lock), so an index can't be served from a read-only mount as built; the deploy needs a writable volume, or an overlay, for data/indexes/<v>/ (files stay read-only and hash-verified). (2026-10-02: confirmed, but only the lock files need write access; deploy/index-permissions.sh, below.)

2026-10-02, host-agnostic build. Nothing names a host; TASK-064 is the owner's.

- deploy/compose.yml runs three services:
  - api: deploy/api.Dockerfile, holding the backend wheel and its locked dependencies; user op-api, uid and gid 10001.
  - web: deploy/web.Dockerfile.
  - caddy: deploy/caddy.Dockerfile, uid 10002; the image's file capability is removed and the namespaced unprivileged-port sysctl lets it bind 80 and 443.
  All three have a read-only root filesystem, cap_drop ALL and no-new-privileges. api and web sit on an internal network with no route out (Docker Engine >= 26.0.0, CVE-2024-29018). --trusted-proxy names Caddy's fixed address, outside the ip_range that api and web are given. Images are tagged OP_IMAGE_TAG, default local. Two one-offs run under the ops profile: ops (op index retire, as root with CHOWN, DAC_OVERRIDE and FOWNER) and takedown-check (as the operator's uid, against http://api:8000).
- deploy/Caddyfile takes the site name from OP_DOMAIN: localhost uses Caddy's local CA, a real name uses ACME. It carries the spec 08 timeouts, body cap and log filters. HSTS comes from OP_HSTS, default max-age=63072000 (the same as the web app's), with includeSubDomains off until TASK-064.
- AC#3:
  - api mounts <data-dir>/takedowns read-only, a directory that holds only withheld.txt. The log lives outside the data directory (decision-022 addendum, 2026-10-02).
  - Tantivy can't open an index from a :ro mount (it writes .tantivy-meta.lock), so indexes/ is mounted read-write and closed by modes: deploy/index-permissions.sh makes a version directory 0750 with group op-api and only its two lock files 0660, and refuses a directory that holds symlinks.
  - records/ is a host directory in the data dir, 0700, uid 10001, with create_host_path false. A host-side retire therefore refuses (records_unreadable) instead of counting no pins.
  - ops keeps CAP_CHOWN: without it, SQLite run as root left root-owned -shm/-wal files and the API's next save returned 500 (reproduced).
- AC#2: the runbook deploy/README.md covers settings, the data layout, permissions, first start (including client addresses), deploying a release, promotion (build, verify, permissions, atomic switch, SIGHUP through init, confirm, takedowns_followed/unmatched, rollback), retire (ops only, pre-checks, restore_failed recovery), takedown steps 1-5 and lifting, backups, the local smoke test, and what remains for the host.
- AC#1, proved locally: deploy/smoke-test.sh (fixture: backend/tests/deploy/fixture_data.py) passed on Docker Desktop 24.0.7 (macOS; the engine-version warning fires there) and on Linux. The Linux run used privileged ubuntu:24.04 docker-in-docker, Docker Engine 29.1.3, run as a non-root account, so the ownership checks ran too. Its output on the deploy/ tree of commit 2bdd9755 (container and build logs left out):
    Docker Engine 29.1.3
    == fixture data directory
    current -> 4184d49daeeb; also built e9db8ab191bf and ccfc75e10556
    takedown list: op:neurips:2019:Fx0001 (unlisted neighbour: op:neurips:2019:Fx0002)
    == build the images (smoke-4200)
    == host setup: the record store and index permissions (as root, as an operator would with sudo)
    /tmp/openproceedings-smoke.A6gkuf/data/indexes/4184d49daeeb: group 10001, directory 0750, lock files 0660
    /tmp/openproceedings-smoke.A6gkuf/data/indexes/e9db8ab191bf: group 10001, directory 0750, lock files 0660
    /tmp/openproceedings-smoke.A6gkuf/data/indexes/ccfc75e10556: group 10001, directory 0750, lock files 0660
    == docker compose up
    api: Up 6 seconds (healthy)
    caddy: Up 5 seconds
    web: Up 6 seconds
    == 1. TLS: healthz and the web root
    {"index_loaded":true,"index_version":"4184d49daeeb","tokenizer_version":"2","query_version":"2"}
    GET / -> 200
    == 2. the api's user and mounts
    uid=10001(op-api) gid=10001(op-api) groups=10001(op-api)
    api can't write /data/takedowns/x: Read-only file system
    api can't write /data/snapshots/x: Read-only file system
    api can't write /data/indexes/4184d49daeeb/x: Permission denied
    api can't write /data/indexes/x: Permission denied
    /data/takedowns holds: withheld.txt
    saved search record ogFkutfmXO1e on 4184d49daeeb
    == 3. promote e9db8ab191bf: repoint current, SIGHUP, /meta
    /api/v1/meta index_version: e9db8ab191bf
    == 4. retire
    retire e9db8ab191bf refused: current points at it
    retire 4184d49daeeb refused: a search record pins it
    retire ccfc75e10556 on the host refused: the record store can't be read
    record ogFkutfmXO1e on its pinned 4184d49daeeb replays: reproduced
    10001 /data/records/records.sqlite
    10001 /data/records/records.sqlite-shm
    10001 /data/records/records.sqlite-wal
    retired ccfc75e10556; e9db8ab191bf still served; the store still takes saves
    backup: 2 search records
    == 5. the takedown
    /api/v1/papers/op:neurips:2019:Fx0001: abstract_withheld, abstract = True None
    /api/v1/papers/op:neurips:2019:Fx0002 (unlisted): abstract_withheld, has an abstract = False True
    0 problem(s): 1 listed id(s) across 2 index version(s), 10 export(s) read
    == 6. no query text in any log
    no log line holds the query (77 lines checked)
    PASS
    rc=0
- Remaining for a real host (stays In Progress):
  - choose the host and domain (TASK-064); DNS and ports 80/443; Docker Engine >= 26.0.0;
  - set OP_DOMAIN, OP_INSTANCE=public, OP_TAKEDOWN_CONTACT and OP_TAKEDOWN_LOG_HOST;
  - host accounts: the operator, and sudo or gid 10001 for index-permissions.sh and records/;
  - first start and checks on the host, including real client addresses (IPv6 through Docker's userland proxy, or a load balancer), rate limits and CORS (TASK-067 AC#2);
  - includeSubDomains in OP_HSTS once the domain is known;
  - the record-store backup schedule.
  No CI job runs smoke-test.sh or builds the api or caddy image; CI's web-image job builds only web.
<!-- SECTION:NOTES:END -->
