---
id: TASK-099
title: '/parse: a machine-readable reading on WARN_MIXED_AND_OR'
status: To Do
assignee: []
created_date: '2026-09-27 21:11'
labels:
  - api
  - frontend
milestone: m-3
dependencies: []
ordinal: 96000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-041's 'Load with parentheses' action extracts the parenthesised reading from the warning's message text. Add an additive field on the diagnostic (e.g. reading: the canonical parenthesised query) so the frontend doesn't parse prose; additive under /api/v1.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The warning carries the reading as a field (additive; test_openapi_additive passes),The editor uses the field and no longer parses message text,Golden test pins the reading for the parser's mixed AND/OR cases
<!-- AC:END -->
