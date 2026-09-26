---
id: TASK-001
title: Decide open query-language semantics before M1
status: To Do
assignee: []
created_date: '2026-09-25 22:06'
updated_date: '2026-09-25 23:20'
labels:
  - query
  - decision
dependencies: []
references:
  - docs/specs/02-query-language.md
  - .claude/skills/query-grammar/SKILL.md
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raised while writing the query/engine and API skills (2026-09-25). Spec 02/04 leave these open; each needs a decision record and a golden test.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decision: does the 3-char minimum stem apply to $ as well as *
- [ ] #2 Decision: wildcard inside a phrase — allowed (expanded per position) or an error
- [ ] #3 Decision: a wildcard stem that normalizes to several tokens (e.g. gpt-4*) — error or phrase-prefix
- [x] #4 Decision: does a track:/status: clause nested inside one OR branch suppress the default for the whole query
- [ ] #5 Decision: canonical sort order of filters
- [ ] #6 Decision: how disjunctive facets treat a filter nested under OR (spec 04)
- [ ] #7 Spec 02/04 updated and golden cases added for every decision
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC4 decided in the 2026-09-25 review round: only top-level AND conjuncts suppress a default; nested track:/status: raises nested_filter (spec 02 §Default filters).

Correction (2026-09-25): the warning code is WARN_NESTED_FILTER (registry style), not nested_filter.
<!-- SECTION:NOTES:END -->
