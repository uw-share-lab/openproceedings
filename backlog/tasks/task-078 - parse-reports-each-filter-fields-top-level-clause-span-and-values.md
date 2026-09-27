---
id: TASK-078
title: /parse reports each filter field's top-level clause span and values
status: To Do
assignee: []
created_date: '2026-09-27 07:21'
updated_date: '2026-09-27 07:46'
labels:
  - api
  - frontend
milestone: m-3
dependencies:
  - TASK-035
ordinal: 76000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in TASK-039. The URL↔state reducer (frontend/src/lib/search-state.ts) rewrites q for facet/include clicks by splicing a FilterClause {source, span, values}: the code-point span of the field's single top-level positive clause in q (zero-width at len(q) when the default applies or the field is unrestricted) and the values it admits. Spec 02 ParseResult has ast (with spans) and defaults, but nothing that hands the UI this per-field summary; deriving it from the AST on the client means walking OR-merged filters and NOT-wrapped clauses in TypeScript, i.e. re-parsing filters (nextjs-conventions forbids it). Add it server-side (spec 02 ParseResult + spec 04), then derive FilterClause from the generated schema.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ParseResult (spec 02) and /parse (spec 04) return, per filter field (track, status, venue, year), the top-level clause's code-point span and values, or a zero-width span at len(q) with the default/all values; a field that cannot be toggled (nested, negated, OR of mixed fields) says so
- [ ] #2 Golden cases pin the spans for typed, default, canonical-pasted and astral-character queries
- [ ] #3 frontend FilterClause is derived from the generated schema (no local type)
- [ ] #4 Each reported clause carries its field and polarity (negated: bool); the frontend offers value toggles only on positive clauses and FilterClause keeps field + negated: false (TASK-039 review)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-039 review: writing an applied default out as (q) AND field:(…) adds one nesting level and about 10+ characters to q, so a q near the limits can fail after a facet click. Add golden cases at PARSE_TOO_DEEP (depth 64) and PARSE_TOO_LONG (2,000 code points) for the wrapped form, and decide whether /parse should report that a field cannot be toggled for such a q.
<!-- SECTION:NOTES:END -->
