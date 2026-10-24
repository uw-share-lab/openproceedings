---
id: TASK-268
title: 'Caddy compare-on: a non-POST request skips the length checks'
status: In Progress
assignee:
  - '@jeevanparmar'
created_date: '2026-10-19 11:49'
updated_date: '2026-10-24 07:06'
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
- [ ] #1 compare-on answers any method but POST with 405 before the length checks
- [ ] #2 deploy/smoke-test.sh --compare has a case for a chunked PUT
- [ ] #3 deploy/README.md and spec 08 say so
<!-- AC:END -->
