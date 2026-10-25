---
id: TASK-255
title: 'Proxy: cut unsized request bodies that stall on the non-compare API routes'
status: In Progress
assignee:
  - '@jeevanparmar'
created_date: '2026-10-16 23:07'
updated_date: '2026-10-25 02:51'
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
- [x] #1 An unsized body that reaches the cap and stalls on any non-compare API route is cut before it holds a connection for read_body, shown by deploy/smoke-test.sh (with and without --compare)
- [x] #2 Spec 08 §Deploy and deploy/README.md describe the bound as built, and the open note is removed
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Review of the follow-ups branch (2026-10-16, security-reviewer): what is at stake is the whole API, not one route. uvicorn's limit_concurrency is 256 (api/config.py), so about 256 unsized bodies that each reach 64 KiB and stall (some 16 MiB in all) could hold every API connection until read_body runs out (60 s with compare.yml, 10 s without), and every other request, searches included, gets uvicorn's 503. That is far cheaper than TASK-256's OOM (400 to 540 MB of fast uploads), so review this task's Low priority against TASK-256. The non-compare behaviour is inferred from the compare-path measurement (docs/results/2026-10-16-compare-proxy.md), not measured on those routes: a GET route might answer and close before the body ends, so measure first. deploy/README.md now states the exposure in its read_body bullet.

2026-10-24: measured on dev: chunked bodies stopped at 65,536 bytes held API connections the full read_body (60 s), GET /search included (BodyLimit reads every method). Fix: request_buffers 65537 (one over the cap) + 411 for any chunked /api/* request (a chunked body past the cap that stalled still held the API: Go drains a closed HTTP/1.1 body). Smoke (both modes): chunked -> 411, unsized HTTP/2 stall at 64 KiB holds 0 API connections. Web paths measured: the app reads no body, nothing held past its 5 s keep-alive. Results: docs/results/2026-10-24-proxy-body-limits.md.
<!-- SECTION:NOTES:END -->
