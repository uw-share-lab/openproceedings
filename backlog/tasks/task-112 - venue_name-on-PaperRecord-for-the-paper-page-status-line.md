---
id: TASK-112
title: venue_name on PaperRecord for the paper page status line
status: To Do
assignee: []
created_date: '2026-09-27 22:46'
labels:
  - api
  - frontend
milestone: m-3
dependencies: []
ordinal: 109000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-042: the paper page reads 'submitted to ICLR 2024' because the full conference name isn't in the API. Add venue_name (additive) from a per-venue-year table.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 venue_name in the record schema and API (additive),Paper page uses it,Table test per venue-year
<!-- AC:END -->
