---
id: TASK-268
title: 'Caddy compare-on: a non-POST request skips the length checks'
status: Done
assignee:
  - '@jeevanparmar'
created_date: '2026-10-19 11:49'
updated_date: '2026-10-26 13:07'
labels:
  - deploy
  - security
dependencies: []
priority: medium
ordinal: 175000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
deploy/Caddyfile's compare-on matchers check only POST, so a PUT (or other method) with a chunked body to /compare skips the content-length checks before reaching the API. Security-gate Nit on the 0.4.0 promotion; already on main. Fix: @notpost not method POST -> 405 in the snippet.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 deploy/smoke-test.sh --compare has a case for a chunked PUT
- [x] #2 deploy/README.md and spec 08 say so
- [x] #3 Only a POST enters compare-on's 16 MiB handle: any other method to /api/v1/compare is an ordinary API request under the 64 KiB cap, a chunked one refused by the proxy (411) and a sized one answered 405 with Allow: POST by the API (revised 2026-10-24 from 'the proxy answers 405': the API's own answer keeps its envelope and lets a CORS preflight through)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24: built as AC #3 (the AC was revised: a proxy 405 would break a CORS preflight and differ from the API's envelope). Smoke --compare: chunked PUT /compare -> 411, sized PUT -> 405 with Allow: POST.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
With comparisons on, only a POST takes the 16 MiB /api/v1/compare path. Other methods stay under the 64 KiB cap and get the API's own 405 (a proxy 405 would break a CORS preflight). smoke --compare: chunked PUT -> 411, sized PUT -> 405 with Allow: POST.
<!-- SECTION:FINAL_SUMMARY:END -->
