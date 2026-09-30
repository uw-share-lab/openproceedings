---
id: TASK-133
title: Takedown contact on public instances (decision-018)
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 00:52'
updated_date: '2026-09-30 01:07'
labels:
  - frontend
  - ops
milestone: m-6
dependencies: []
ordinal: 116000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-018 (serve every abstract) requires a takedown contact on every page of a public instance; private, local and development deployments may omit it. TASK-063 found none anywhere (no footer or about page, nothing in the API or docs).

Proposed procedure, not yet decided (settle it here): a takedown withholds that record's abstract from the next index_version; the record stays, matched on title, as a missing abstract already is (spec 01 §Error handling).

Known gap: older index_versions still serve the abstract while search records pin them, because op index retire refuses to retire a pinned version (spec 08 §CLI). Decide how a takedown reaches them (e.g. an abstract-withheld overlay at serve time, or accepting that pinned versions keep it) and record the choice.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The frontend shows a takedown contact on every page (footer or about page), with copy reviewed by ux-writer
- [ ] #2 The takedown procedure is documented (spec 08 §Deploy / runbook): who receives requests, how an abstract is removed from the next index version, and how that is recorded
- [ ] #3 Tests pin the contact's presence
<!-- AC:END -->
