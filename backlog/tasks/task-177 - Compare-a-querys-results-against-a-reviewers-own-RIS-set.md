---
id: TASK-177
title: Compare a query's results against a reviewer's own RIS set
status: To Do
assignee: []
created_date: '2026-10-05 01:47'
labels:
  - api
  - frontend
  - eval
  - ux
milestone: m-3
dependencies:
  - TASK-056
references:
  - docs/specs/07-evaluation.md
  - docs/specs/04-backend-api.md
ordinal: 121000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A reviewer moving from Google Scholar to openproceedings asks what they lose and gain: which of the records they already hold does this query keep, which does it drop, and which does it add. On 2026-10-04 this was answered for the Trust-Evals review by script (51 kept, 1,754 dropped, 16 added). TASK-056 builds the matching and classification for the report; this task makes the same comparison available to any user for their own RIS file.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Given a RIS file and a query, the user sees the counts and lists of records kept, dropped and added, with records matched to the index by the merge rules of spec 01, and records that are not in the index reported separately
- [ ] #2 The comparison reuses TASK-056's matching code; there is one implementation
- [ ] #3 An upload is size- and record-capped, parsed without executing or storing it, never logged (logging-standards), and reviewed by security-reviewer; the design says whether it runs in the CLI only or also on a public instance, and why
- [ ] #4 The comparison never changes the query's result set (00 guarantee 5), and the kept, dropped and added lists are exportable
- [ ] #5 Specs and help as built
<!-- AC:END -->
