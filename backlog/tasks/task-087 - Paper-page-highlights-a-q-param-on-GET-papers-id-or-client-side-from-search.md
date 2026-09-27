---
id: TASK-087
title: >-
  Paper page highlights: a q param on GET /papers/{id}, or client-side from
  /search
status: To Do
assignee: []
created_date: '2026-09-27 11:33'
labels:
  - api
  - frontend
milestone: m-3
dependencies:
  - TASK-035
ordinal: 85000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found at the M3a docs gate. Spec 05 §Pages has /paper/[id] show the abstract with the current query's highlights, but GET /papers/{id} (spec 04) takes no q and returns no highlights, and the client may not re-match (spec 05 §Components 6; nextjs-conventions). Either add an optional q (+ mode) to GET /papers/{id} that returns highlights computed by engine/highlight.py exactly as /search does (additive under v1: a new optional parameter, a new always-sent field), or carry the hit's highlights from the /search response the reader came from (then a direct link to /paper/[id] shows none). Decide, update spec 04/05, make openapi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Spec 04 and 05 say how /paper/[id] gets its highlights, and a direct link without q is handled
- [ ] #2 If the API route changes: contract test for highlights equal to /search's for the same q, record and index; openapi snapshot and schema.ts regenerated
<!-- AC:END -->
