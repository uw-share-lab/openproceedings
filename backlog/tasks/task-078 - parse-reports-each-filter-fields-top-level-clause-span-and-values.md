---
id: TASK-078
title: /parse reports each filter field's top-level clause span and values
status: To Do
assignee: []
created_date: '2026-09-27 07:21'
updated_date: '2026-09-27 13:24'
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
- [ ] #5 "Top-level" is judged on the flattened canonical tree (parenthesised AND groups are flattened): when a field has more than one top-level clause there, e.g. track:workshop "large language model" AND (venue:NeurIPS track:workshop), /parse reports no editable clause for that field with the reason, and the frontend passes clause: null so the reducer's NO_EDITABLE_CLAUSE disables the facet (M3a gate, query-semantics review)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-039 review: writing an applied default out as (q) AND field:(…) adds one nesting level and about 10+ characters to q, so a q near the limits can fail after a facet click. Add golden cases at PARSE_TOO_DEEP (depth 64) and PARSE_TOO_LONG (2,000 code points) for the wrapped form, and decide whether /parse should report that a field cannot be toggled for such a q.

TASK-035 (2026-09-27) left this open: /parse now returns 02's ParseResult (ast with spans, effective_ast, defaults), but the per-field clause summary is a new public shape spec 02/04 don't define yet. It needs a spec decision first: (a) the name and placement (e.g. ParseResult.filters: {venue|year|track|status: {span, values, toggleable, reason?}}), (b) how year is represented (ranges, not a value list), (c) what 'cannot be toggled' carries (nested under OR, negated, OR of mixed fields), (d) the values for an unrestricted field (all /meta values, or empty + a flag). The server-side derivation belongs in query/ (e.g. defaults.py beside the top-level conjunct logic), not in the router. AC3 also waits on TASK-040's codegen.

M3a gate (decision-008): the length cap now also applies to the CANONICAL form, which adds ~4 characters per implicit AND plus the defaults. A facet click's wrapped q can therefore pass the frontend's raw 2,000-code-point check and still be refused by the server. /parse should report a filter field as not toggleable (reason: would exceed the cap) when the canonical of the wrapped form would exceed MAX_QUERY_LENGTH.

M3a review gate round 3: /meta could also expose the instance's serving limits a client needs to explain a refusal before it happens: `max_verified_clauses` (and `max_verification_candidates`, decision-010) and the query-length cap (`MAX_QUERY_LENGTH`, 2,000 code points), so the search box can warn as the user types and the record page can say by how much a withheld replay is over the limit. Additive to MetaResponse; scope it with this task or split it out.
<!-- SECTION:NOTES:END -->
