---
id: TASK-183
title: Smoke-test the Caddy block that enables comparisons on a public instance
status: To Do
assignee: []
created_date: '2026-10-05 08:39'
labels:
  - ops
  - security
milestone: m-6
dependencies: []
ordinal: 127000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-035 makes this a precondition: deploy/README.md's Caddy snippet for an instance run with --compare has never been through deploy/smoke-test.sh (its image builds need network, which TASK-177's sessions lacked). That block is what keeps a slow upload off the single comparison slot.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The enabled stack passes smoke-test.sh with a comparison upload, a stalled upload is cut by the proxy before it holds the slot, and the README's untested note is removed or the block corrected
<!-- AC:END -->
