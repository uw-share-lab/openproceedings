---
id: TASK-065
title: 'Deploy: compose, Caddy TLS, index promotion runbook'
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-10-02 18:51'
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
From the task-023 review (2026-09-26): a Tantivy index directory must be writable to open (readers take .tantivy-meta.lock), so an index can't be served from a read-only mount as built; the deploy needs a writable volume, or an overlay, for data/indexes/<v>/ (files stay read-only and hash-verified).

2026-10-02, host-agnostic build (nothing names a host; TASK-064 is the owner's):
- deploy/compose.yml runs api (deploy/api.Dockerfile: the backend wheel and its locked dependencies, user op-api, uid and gid 10001), web (deploy/web.Dockerfile) and caddy (deploy/caddy.Dockerfile, uid 10002). Every container has a read-only root filesystem, cap_drop ALL and no-new-privileges. api and web sit on an internal network with no route out. --trusted-proxy names Caddy's fixed address, outside the ip_range that api and web are given. Two one-offs run under the ops profile: ops (op index retire) and takedown-check.
- deploy/Caddyfile takes the site name from OP_DOMAIN: localhost uses Caddy's local CA, a real name uses ACME. It carries the spec 08 timeouts, body cap and log filters. HSTS comes from OP_HSTS, default max-age=63072000 (the same as the web app's), with includeSubDomains left off until TASK-064 decides the domain.
- AC#3: api mounts <data-dir>/takedowns read-only, a directory that holds only withheld.txt. The log lives outside the data directory, per a decision-022 addendum, and the takedown-check service reads it as the operator's uid. Tantivy can't open an index from a :ro mount (it writes .tantivy-meta.lock), so indexes/ is mounted read-write and closed by file modes: deploy/index-permissions.sh makes a version directory 0750 with group op-api and only its two lock files 0660. Records are a named volume owned by op-api. The ops service keeps CAP_CHOWN: without it, SQLite run as root left root-owned -shm/-wal files and the API's next save returned 500 (reproduced).
- AC#2: the runbook deploy/README.md covers settings, the data layout, permissions, first start, promotion (build, permissions, ln -sfn, SIGHUP through init, confirm /meta, rollback), retire, takedowns, and what remains for the host.
- AC#1, proved locally: deploy/smoke-test.sh (fixture: backend/tests/deploy/fixture_data.py) passed on Docker Desktop 24.0.7 (macOS), and on Linux in privileged ubuntu:24.04 docker-in-docker, run as a non-root account, where the ownership checks also ran. Output (Linux run):
  == 1. TLS: healthz and the web root
  {"index_loaded":true,"index_version":"4184d49daeeb","tokenizer_version":"2","query_version":"2"}
  GET / -> 200
  == 2. the api's user and mounts
  uid=10001(op-api) gid=10001(op-api) groups=10001(op-api)
  api can't write /data/takedowns/x, /data/snapshots/x, /data/indexes/4184d49daeeb/x, /data/indexes/x; /data/takedowns holds withheld.txt only
  == 3. promote e9db8ab191bf: repoint current, SIGHUP, /meta -> e9db8ab191bf
  == 4. retire: refused for current; refused for 4184d49daeeb (1 search record pins it; that record replays reproduced); ccfc75e10556 retired; the record store's files all uid 10001; a save after retire works
  == 5. the takedown: /api/v1/papers/op:neurips:2019:Fx0000 abstract_withheld True, abstract None; op takedown check: 0 problem(s), 1 listed id across 2 index versions, 10 exports read
  == 6. no log line holds the query
  PASS
  Manual curl through Caddy on macOS (curl --cacert <Caddy local root> https://localhost/api/v1/healthz): HTTP/2 200, strict-transport-security: max-age=63072000, cache-control: no-store, via: 1.1 Caddy, body {"index_loaded":true,"index_version":"4184d49daeeb",...}. GET https://localhost/ returned HTTP/2 200 with the web app's CSP. http://localhost/ returned 308 to https.
- Remaining for a real host (stays In Progress): choose the host and domain (TASK-064); DNS and ports 80/443; OP_DOMAIN, OP_INSTANCE=public, OP_TAKEDOWN_CONTACT, OP_TAKEDOWN_LOG_HOST; host accounts (operator, and gid 10001 for index-permissions.sh, or sudo); first start and checks on the host, including rate limits and CORS (TASK-067 AC#2); includeSubDomains in OP_HSTS once the domain is known; a backup of the records volume. No CI job runs smoke-test.sh or builds the api or caddy image yet (CI's web-image job builds only the web image).
<!-- SECTION:NOTES:END -->
