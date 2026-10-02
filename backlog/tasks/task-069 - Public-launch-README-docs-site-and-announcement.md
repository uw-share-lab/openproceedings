---
id: TASK-069
title: 'Public launch: README, docs site and announcement'
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-10-02 18:57'
labels:
  - docs
milestone: m-6
dependencies:
  - TASK-063
  - TASK-065
  - TASK-066
  - TASK-067
  - TASK-068
  - TASK-133
  - TASK-134
  - TASK-136
  - TASK-138
ordinal: 68000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
README and CONTRIBUTING as-built for external users; citation info.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 README quickstart verified on a clean machine
- [ ] #2 CITATION.cff added
- [ ] #3 Repo visibility is public and README links the instance (spec 00 §Milestones M6)
- [ ] #4 Public instance reachable over TLS with the current index_version on /healthz
- [ ] #5 The outcome of the copyright-office consultation (TASK-135, recommended, not blocking), if any, is recorded before launch
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-02, AC#1: verified the README quickstart on a clean machine: a fresh ubuntu:24.04 container (arm64), as a non-root user, with only what the README lists installed: uv by its installer (it fetched CPython 3.12; the image had no Python), Node 22.23.3 and npm 10.9.9 from nodejs.org, shellcheck, and git and make (added to the list; see below). The repository was copied in as a clone (git init and one commit). Transcript summary:
- 2. scripts/setup-dev.sh: hooks set and .env created (it prints the Backlog.md hint). make sync: uv sync --locked and npm ci --ignore-scripts, OK. uv run op --help: OK.
- 3. uv run op ingest neurips --year 2013 --dry-run: 1 request, 360 listed. The real crawl made 360 requests in 9 min 25 s (the README says at least 6 min): 360 records, 0 abstracts missing, count_ok.
- 4. op snapshot build created 2026-10-02-01bea378653b. op index build created 251af89ddeb4. ln -sfn current. op search "trust AND calibration": the PRISMA header with 0 identified, which is correct for NeurIPS 2013 alone. "neural AND network": 12. op export … --format ris --out results.ris: 12 TY records.
- 5. op serve --cors-origin http://localhost:3000: /api/v1/healthz returned index_loaded true, /api/v1/docs 200, and a request with Origin http://localhost:3000 got access-control-allow-origin.
- 6. npm run dev with NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000: GET / 200 (title openproceedings), /search?q=… 200. npm run build, then npm run start with PORT=3000 HOSTNAME=127.0.0.1: GET / 200.
- 7. op eval coverage --index 251af89ddeb4 wrote docs/results/2026-10-02-coverage.md. --check exits 1 (the gate fails on a one-year crawl, as expected).
- make lint passed in the same container.
README fixes from the run: the quickstart had no clone step (added: git clone … && cd openproceedings); git and make were missing from the prerequisites (added); shellcheck now names apt-get too; uv provides Python 3.12 when it is missing (said); the search example now says what a 2013-only crawl returns, and the export example uses a real query instead of a placeholder.
AC#2: CITATION.cff added and valid against the CFF 1.2.0 schema (uvx cffconvert --validate: 'Citation metadata are valid according to schema version 1.2.0'). The author list is pending from team-lead: Jeevan Parmar plus a placeholder entry. Left unchecked until the real list is in.
<!-- SECTION:NOTES:END -->
