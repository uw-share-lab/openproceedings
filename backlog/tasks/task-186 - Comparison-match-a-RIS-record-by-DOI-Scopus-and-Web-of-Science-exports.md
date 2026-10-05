---
id: TASK-186
title: 'Comparison: match a RIS record by DOI (Scopus and Web of Science exports)'
status: To Do
assignee: []
created_date: '2026-10-05 08:39'
labels:
  - eval
  - ingest
milestone: m-3
dependencies: []
ordinal: 130000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The comparison matches by OpenReview forum id, proceedings id and title with venue and year. Exports from Scopus and Web of Science carry DOIs and often lack the URLs those rules read, so their records fall to title matching or not_in_index.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A DOI that names an indexed paper matches it under a rule stated in spec 07, never across venue or year, with fixtures from both export formats
<!-- AC:END -->
