---
id: TASK-040
title: OpenAPI snapshot and generated TypeScript types
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
labels:
  - api
  - frontend
milestone: m-3
dependencies:
  - TASK-035
  - TASK-039
ordinal: 39000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
op openapi → frontend/src/api/schema.ts; CI freshness check (api-contract skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 OpenAPI snapshot test shows contract changes in PR diffs
- [ ] #2 CI fails if schema.ts is stale
<!-- AC:END -->
