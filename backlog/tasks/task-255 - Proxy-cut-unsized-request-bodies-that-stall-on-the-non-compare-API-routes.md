---
id: TASK-255
title: 'Proxy: cut unsized request bodies that stall on the non-compare API routes'
status: To Do
assignee: []
created_date: '2026-10-16 23:07'
updated_date: '2026-10-16 23:17'
labels:
  - ops
  - security
dependencies: []
priority: low
ordinal: 168000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-183 (PR #156, docs/results/2026-10-16-compare-proxy.md). The compare-on block answers 411 to a POST to /api/v1/compare with no Content-Length, but the other API routes still stream a body through once it passes request_buffers: an unsized (chunked) body that reaches the 64KiB site cap and then stalls holds a uvicorn connection until read_body, which deploy/compare.yml raises to 60 s. Fix candidates: a 411 for unsized POSTs on every API route, or request_buffers set one byte over the 64KiB cap so the cap fires before streaming. Spec 08 §Deploy marks this open.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An unsized body that reaches the cap and stalls on any non-compare API route is cut before it holds a connection for read_body, shown by deploy/smoke-test.sh (with and without --compare)
- [ ] #2 Spec 08 §Deploy and deploy/README.md describe the bound as built, and the open note is removed
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Review of the follow-ups branch (2026-10-16, security-reviewer): what is at stake is the whole API, not one route. uvicorn's limit_concurrency is 256 (api/config.py), so about 256 unsized bodies that each reach 64 KiB and stall (some 16 MiB in all) could hold every API connection until read_body runs out (60 s with compare.yml, 10 s without), and every other request, searches included, gets uvicorn's 503. That is far cheaper than TASK-256's OOM (400 to 540 MB of fast uploads), so review this task's Low priority against TASK-256. The non-compare behaviour is inferred from the compare-path measurement (docs/results/2026-10-16-compare-proxy.md), not measured on those routes: a GET route might answer and close before the body ends, so measure first. deploy/README.md now states the exposure in its read_body bullet.
<!-- SECTION:NOTES:END -->
