---
id: TASK-035
title: 'Endpoints: /parse, /search, /papers, /meta'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 01:51'
labels:
  - api
milestone: m-3
dependencies:
  - TASK-034
ordinal: 34000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 04 §Endpoints and SearchResponse.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 SearchResponse has query (canonical, identification_query, warnings, translations, expansions), index/tokenizer/query versions, total, excluded, disjunctive facets, hits
- [ ] #2 Parse errors are 422 with diagnostics; spans per spec 04
- [ ] #3 Contract tests on the fixture index
- [ ] #4 Contract test (decision-001): a facet removes only top-level conjuncts of its own field; a filter nested under OR stays applied
<!-- AC:END -->
