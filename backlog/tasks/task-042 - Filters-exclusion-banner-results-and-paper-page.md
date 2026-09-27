---
id: TASK-042
title: 'Filters, exclusion banner, results and paper page'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 12:11'
labels:
  - frontend
milestone: m-3
dependencies:
  - TASK-041
  - TASK-035
  - TASK-087
  - TASK-078
ordinal: 41000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 05 §Components 4–6.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Filter and facet clicks rewrite q; workshop off by default
- [ ] #2 Banner itemises unknown; each include label shows the real facet delta
- [ ] #3 Highlights rendered from API spans only; /paper/[id] with provenance
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Facet/include clicks go through reduce() in src/lib/search-state.ts (TASK-039); its FilterClause input needs per-field clause spans from /parse, which is TASK-078.
<!-- SECTION:NOTES:END -->
