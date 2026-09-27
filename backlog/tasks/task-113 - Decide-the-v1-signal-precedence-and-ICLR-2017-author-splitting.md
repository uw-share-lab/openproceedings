---
id: TASK-113
title: Decide the v1 signal precedence and ICLR 2017 author splitting
status: To Do
assignee: []
created_date: '2026-09-27 22:46'
labels:
  - ingest
  - docs
milestone: m-4
dependencies: []
ordinal: 110000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-051 leaves a field unknown when two v1 signals disagree (e.g. a withdrawn invitation vs an accepting venue string), and leaves ICLR 2017 single-string authors empty. Decide whether one signal outranks another, and how to split the author strings once a real one is recorded. Also document the new unresolved conflict type in the manifest's conflict counts (spec 01/07).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decision records the precedence (or that unknown stays),A decision or spec rule for ICLR 2017 authors,Spec 01/07 document the unresolved conflict type
<!-- AC:END -->
