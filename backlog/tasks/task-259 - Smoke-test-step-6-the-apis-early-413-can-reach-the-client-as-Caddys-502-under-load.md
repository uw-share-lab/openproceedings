---
id: TASK-259
title: >-
  Smoke test step 6: the api's early 413 can reach the client as Caddy's 502
  under load
status: To Do
assignee: []
created_date: '2026-10-18 04:43'
labels:
  - ops
  - deploy
  - flaky
dependencies: []
priority: medium
ordinal: 172000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the 2026-10-17 Dependabot batch (#163): deploy/smoke-test.sh step 6 (64 KiB + 1 byte to /api/v1/records) failed once at load about 20 with 502 instead of 413. The api logged 413 API_BODY_TOO_LARGE in 0.3 ms and closed the connection; Caddy, still streaming the body upstream (65536 of 65537 bytes read), logged 'write: connection reset by peer' and returned 502. It passed on dev 22947899 and on a rerun of the PR head at load about 6. Plausibly a race between the api's early reply and Caddy's proxying since #156 (TASK-183) changed the Caddy config; not proven.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The race is reproduced or ruled out with a repeated run of step 6 under load (N and load recorded)
- [ ] #2 If real: a client over the records body limit always gets 413, not 502, and smoke-test.sh asserts it stably; if not real: step 6 is made robust and the cause recorded
<!-- AC:END -->
