---
id: TASK-064
title: 'Decide: hosting location'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-10-16 15:37'
labels:
  - decision
  - ops
milestone: m-6
dependencies: []
ordinal: 63000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 00 open question 5: lab VM, university server or PaaS.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decision recorded with costs and ops owner
- [ ] #2 Spec 00 §Open questions Q5 closed; spec 08 §Deploy names the host
- [ ] #3 The chosen host meets the requirements in the 2026-10-16 note (containers, DNS name and 80/443, disk for retained versions, a scheduler, outbound access to the crawl hosts), or the decision says which are dropped and why
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-16, what the host must provide (the deploy as built since TASK-065, for comparing candidates; no candidate chosen):
- Containers: docker compose (api, web, Caddy, plus the ops and takedown-check one-offs; deploy/README.md). TLS through ACME needs a public DNS name and inbound 80/443.
- Disk: per index version about 293 MB of index (b4f335e07e70) and 1.1 GB of snapshot (2026-10-11-93c2937e2f29); op serve holds up to --pinned-indexes (default 4) older versions open, and retention keeps what saved searches pin, so plan for several versions plus the crawl cache. RAM is unmeasured: measure it on the candidate host.
- Domain: HSTS includeSubDomains is ON for a dedicated domain and OFF for a subdomain of someone else's (e.g. uwaterloo.ca) (owner, 2026-10-01).
- Takedowns: the log is a host file outside the repo, operator-only, mode 0600 (owner, 2026-09-30); withheld.txt is mounted as a directory holding only that file; the public web build needs NEXT_PUBLIC_TAKEDOWN_CONTACT.
- Scheduled jobs (TASK-202): a scheduler (cron or similar), the OpenReview login in the host's .env, and outbound HTTPS to every crawl host (openreview.net, the ICLR archive, proceedings.neurips.cc, proceedings.mlr.press, ojs.aaai.org, api.crossref.org, facctconference.org, api.openalex.org, web.archive.org).
- Comparisons (--compare) need the Caddy block TASK-183 tests, with a memory limit on the caddy service.
- Semantic layer: none. decision-017's addendum (2026-10-16) shelves it, so no model or vector RAM is needed.
<!-- SECTION:NOTES:END -->
