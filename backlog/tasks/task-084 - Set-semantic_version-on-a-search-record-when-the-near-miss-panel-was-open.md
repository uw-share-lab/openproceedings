---
id: TASK-084
title: Set semantic_version on a search record when the near-miss panel was open
status: To Do
assignee: []
created_date: '2026-09-27 08:44'
labels:
  - api
  - records
  - semantic
dependencies:
  - TASK-060
  - TASK-062
ordinal: 82000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 04 §Search records: a record stores semantic_version if the near-miss panel was open (the audit trail for query revisions it prompted; never an input to ids_hash). task-037 stores null until the panel exists. Decide how POST /records learns the panel was open without trusting a client-supplied version string (e.g. a boolean the server maps to its own semantic_version), and store it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 POST /records records the server's semantic_version when the panel was open, null otherwise; a client can't set an arbitrary version
- [ ] #2 ids_hash and replay status are unaffected by semantic_version (test)
- [ ] #3 Spec 04 and the search-records skill updated
<!-- AC:END -->
