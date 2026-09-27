---
id: TASK-089
title: /meta exposes the query-length cap and verification limits
status: To Do
assignee: []
created_date: '2026-09-27 18:14'
labels:
  - api
milestone: m-3
dependencies: []
ordinal: 87000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-078's round-3 note: clients can't discover MAX_QUERY_LENGTH (2,000), max_verified_clauses (16) or max_verification_candidates (300,000), so the frontend hard-codes the cap. Add them to GET /meta additively (v1 frozen: required new fields per the contract rules) and derive the frontend's constant from it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 GET /meta returns the three limits; OpenAPI snapshot and schema.ts regenerated
- [ ] #2 frontend MAX_QUERY_LENGTH comes from /meta (or the generated type) instead of a hand-kept constant
<!-- AC:END -->
