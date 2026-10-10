---
id: TASK-221
title: 'Re-check two OJS section labels live (AAAI v38 AI24-43, AIES v8 A25-SA)'
status: To Do
assignee: []
created_date: '2026-10-10 05:14'
labels:
  - ingest
  - new-venues
milestone: m-4
dependencies: []
ordinal: 154000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raised by the milestone A review gate: the labels of AAAI Vol. 38 set AI24-43 and AIES Vol. 8 set A25-SA in ingest/ojs_sections.toml were taken from ListSets but couldn't be cross-checked against the issue pages without network access during the fix round. Fetch the two issue pages once and confirm label and track; fix the rows if they differ (a snapshot-diff event).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Both labels confirmed against the live issue pages, rows fixed if needed
<!-- AC:END -->
