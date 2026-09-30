---
id: TASK-133
title: Takedown contact on every deployment (decision-018)
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 00:52'
labels:
  - frontend
  - ops
milestone: m-6
dependencies: []
ordinal: 116000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-018 (serve every abstract) requires a takedown contact on every deployment; TASK-063 found none anywhere (no footer or about page, nothing in the API or docs). A takedown removes that record's abstract from the next index version.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The frontend shows a takedown contact on every page (footer or about page), with copy reviewed by ux-writer
- [ ] #2 The takedown procedure is documented (spec 08 §Deploy / runbook): who receives requests, how an abstract is removed from the next index version, and how that is recorded
- [ ] #3 Tests pin the contact's presence
<!-- AC:END -->
