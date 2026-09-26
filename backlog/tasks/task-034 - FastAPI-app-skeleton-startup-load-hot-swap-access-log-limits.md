---
id: TASK-034
title: 'FastAPI app skeleton: startup load, hot-swap, access log, limits'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
labels:
  - api
milestone: m-3
dependencies:
  - TASK-030
ordinal: 33000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 04 §Conventions and §Implementation notes (fastapi-conventions, logging-standards skills).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Index loaded once; atomic hot-swap on SIGHUP; exports in flight finish on their index
- [ ] #2 One JSON access line per request with the logging-standards fields; no query text
- [ ] #3 Per-IP rate limit and CORS allowlist from config; /healthz
<!-- AC:END -->
