---
id: TASK-109
title: Warn when a venue-year holds a status its sources cannot supply
status: To Do
assignee: []
created_date: '2026-09-27 22:46'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 106000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-082: statuses_indexed also includes any status the records actually hold, which can hide an error in the per-source status table (synthetic data showed ICML 2019 accepted+withdrawn). Log and report such cells instead of silently widening.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Snapshot build reports each unexpected (venue-year, status) with the records behind it,Test with a synthetic record
<!-- AC:END -->
