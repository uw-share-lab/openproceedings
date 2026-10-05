---
id: TASK-185
title: >-
  Comparison: a file's paper outside the query's own year or venue limit needs
  its own class
status: To Do
assignee: []
created_date: '2026-10-05 08:39'
labels:
  - eval
  - api
milestone: m-3
dependencies: []
ordinal: 129000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-177 found that eval/scholar_compare.py classes a file record that the query's own year: or venue: clause excludes as full_text, which tells the reviewer the text did not match when the filter did the excluding.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Such a record is reported with a class and reason naming the query's own limit, in op eval scholar and POST /compare, with tests; spec 07 and the protocol skill state it
<!-- AC:END -->
