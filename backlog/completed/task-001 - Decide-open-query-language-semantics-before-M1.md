---
id: TASK-001
title: Decide open query-language semantics before M1
status: Done
assignee: []
created_date: '2026-09-25 22:06'
updated_date: '2026-09-26 01:51'
labels:
  - query
  - decision
milestone: m-1
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
- [x] #1 Decision: does the 3-char minimum stem apply to $ as well as *
- [x] #2 Decision: wildcard inside a phrase — allowed (expanded per position) or an error
- [x] #3 Decision: a wildcard stem that normalizes to several tokens (e.g. gpt-4*) — error or phrase-prefix
- [x] #4 Decision: does a track:/status: clause nested inside one OR branch suppress the default for the whole query
- [x] #5 Decision: canonical sort order of filters
- [x] #6 Decision: how disjunctive facets treat a filter nested under OR (spec 04)
- [x] #7 Spec 02/04 updated; each decision's golden case assigned as an AC to task-011, 012, 013 or 035 (the tasks that build the code it tests)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC4 decided in the 2026-09-25 review round: only top-level AND conjuncts suppress a default; nested track:/status: raises nested_filter (spec 02 §Default filters).

Correction (2026-09-25): the warning code is WARN_NESTED_FILTER (registry style), not nested_filter.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Recorded in backlog decision-001: `$` shares the 3-char stem minimum (counted over the whole written stem); wildcards inside phrases expand per position; a multi-token wildcard stem becomes a phrase with the wildcard on its last token; canonical filter order venue, year, track, status, then alphabetical, with values sorted; facets drop only top-level conjuncts of their own field. Spec 02 (§Grammar rules, §Outputs) and spec 04 (facets) updated. Golden cases are ACs on task-011/012/013/035.
<!-- SECTION:FINAL_SUMMARY:END -->
