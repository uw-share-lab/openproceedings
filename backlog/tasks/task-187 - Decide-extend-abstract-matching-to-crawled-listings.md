---
id: TASK-187
title: 'Decide: extend abstract matching to crawled listings'
status: To Do
assignee: []
created_date: '2026-10-05 08:39'
labels:
  - ingest
  - dedup
  - decision
milestone: m-4
dependencies: []
ordinal: 131000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-037 limits the abstract_venue_year merge to import-only clusters. On snapshot 2026-10-05-10b5a205a63f exactly one crawled pair would merge if it were extended: NeurIPS 2023 D&B note 3sRR2u72oQ and its retitled proceedings listing nips-39736af1…; 1,706 other same-abstract groups are twins or duplicate submissions that must stay apart.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The owner's decision is recorded; if extended, the rule names what distinguishes a retitled listing from a twin, with the real pair and negative cases as tests
<!-- AC:END -->
