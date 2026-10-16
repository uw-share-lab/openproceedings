---
id: TASK-257
title: >-
  Test an HTTP/3 upload stall and re-enable HTTP/3 with comparisons on if it is
  cut
status: To Do
assignee: []
created_date: '2026-10-16 23:07'
labels:
  - ops
dependencies: []
priority: low
ordinal: 170000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-183 (PR #156) turns HTTP/3 off in the compare-on block because a stalled upload over QUIC couldn't be tested: the Mac's curl has no HTTP/3. Since Caddy 2.11.6 the per-request read deadline (read_body_idle, and read_body) probably reaches QUIC streams. Test it with an HTTP/3-capable client against smoke-test.sh --compare.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An HTTP/3 upload that stalls is shown to be cut by the proxy before it holds the comparison slot, or shown not to be; HTTP/3 is re-enabled in compare-on only if it is cut, and spec 08 and deploy/README.md say which
<!-- AC:END -->
