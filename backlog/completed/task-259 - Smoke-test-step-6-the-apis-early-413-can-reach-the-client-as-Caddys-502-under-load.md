---
id: TASK-259
title: >-
  Smoke test step 6: the api's early 413 can reach the client as Caddy's 502
  under load
status: Done
assignee:
  - '@jeevanparmar'
created_date: '2026-10-18 04:43'
updated_date: '2026-10-26 13:07'
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
- [x] #1 The race is reproduced or ruled out with a repeated run of step 6 under load (N and load recorded)
- [x] #2 If real: a client over the records body limit always gets 413, not 502, and smoke-test.sh asserts it stably; if not real: step 6 is made robust and the cause recorded
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-18: the owner accepted the step-6 failure on #163 as a load flake (PR comment 6245774509) after it passed on dev 22947899 and on a rerun of the PR head.

2026-10-24: reproduced: 150 tries per protocol under 8 busy loops (host load 14-35): HTTP/1.1 133 Caddy 413 / 12 API 413 / 5 x 502; HTTP/2 141/5/4 (broken pipe: the API refused from the header and closed mid-send). Fix in the proxy: a declared length over 64 KiB gets error 413 before any body is read, and handle_errors 413 answers in the API's exact envelope. After: 300/300 API-envelope 413 at load ~230. Smoke step 6 sends it 20x over HTTP/1.1 and HTTP/2 and compares byte for byte with the API's own 413.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The early 413 could reach a client as Caddy's 502 under load (reproduced 5/150 over HTTP/1.1, 4/150 over HTTP/2). Now a declared length over 64 KiB gets the proxy's 413 before any body is read. handle_errors 413 answers in the API's exact envelope, with Connection: close only over HTTP/1.x. After: 300/300 envelope 413s at load ~230. Smoke step 6 sends it 20x per protocol and compares byte for byte with the API's own 413.
<!-- SECTION:FINAL_SUMMARY:END -->
