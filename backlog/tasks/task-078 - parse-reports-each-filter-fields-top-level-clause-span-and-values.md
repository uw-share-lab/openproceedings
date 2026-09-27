---
id: TASK-078
title: /parse reports each filter field's top-level clause span and values
status: Done
assignee:
  - '@api-engineer'
created_date: '2026-09-27 07:21'
updated_date: '2026-09-27 18:13'
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
- [x] #1 ParseResult (spec 02) and /parse (spec 04) return, per filter field (track, status, venue, year), the top-level clause's code-point span and values, or a zero-width span at len(q) with the default/all values; a field that cannot be toggled (nested, negated, OR of mixed fields) says so
- [x] #2 Golden cases pin the spans for typed, default, canonical-pasted and astral-character queries
- [x] #3 frontend FilterClause is derived from the generated schema (no local type)
- [x] #4 Each reported clause carries its field and polarity (negated: bool); the frontend offers value toggles only on positive clauses and FilterClause keeps field + negated: false (TASK-039 review)
- [x] #5 "Top-level" is judged on the flattened canonical tree (parenthesised AND groups are flattened): when a field has more than one top-level clause there, e.g. track:workshop "large language model" AND (venue:NeurIPS track:workshop), /parse reports no editable clause for that field with the reason, and the frontend passes clause: null so the reducer's NO_EDITABLE_CLAUSE disables the facet (M3a gate, query-semantics review)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. query/clauses.py: filter_clauses(q, parse(q, mode)) -> ParsedFilters on the flattened canonical tree; widest-edit cap check by parsing the edited string. 2. POST /parse serves it as filters (additive, required, null on errors); open enum 'clause reason'; make openapi. 3. Shared golden frontend/src/lib/filter-clause-golden.json (backend unit + contract + reducer). 4. Reducer: FilterClause derived from generated ParsedClause via clauseFromParse; reasons worded (TOO_DEEP new). 5. Specs 02/04/05, skills, CLAUDE.md, decision-011.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-039 review: writing an applied default out as (q) AND field:(…) adds one nesting level and about 10+ characters to q, so a q near the limits can fail after a facet click. Add golden cases at PARSE_TOO_DEEP (depth 64) and PARSE_TOO_LONG (2,000 code points) for the wrapped form, and decide whether /parse should report that a field cannot be toggled for such a q.

TASK-035 (2026-09-27) left this open: /parse now returns 02's ParseResult (ast with spans, effective_ast, defaults), but the per-field clause summary is a new public shape spec 02/04 don't define yet. It needs a spec decision first: (a) the name and placement (e.g. ParseResult.filters: {venue|year|track|status: {span, values, toggleable, reason?}}), (b) how year is represented (ranges, not a value list), (c) what 'cannot be toggled' carries (nested under OR, negated, OR of mixed fields), (d) the values for an unrestricted field (all /meta values, or empty + a flag). The server-side derivation belongs in query/ (e.g. defaults.py beside the top-level conjunct logic), not in the router. AC3 also waits on TASK-040's codegen.

M3a gate (decision-008): the length cap now also applies to the CANONICAL form, which adds ~4 characters per implicit AND plus the defaults. A facet click's wrapped q can therefore pass the frontend's raw 2,000-code-point check and still be refused by the server. /parse should report a filter field as not toggleable (reason: would exceed the cap) when the canonical of the wrapped form would exceed MAX_QUERY_LENGTH.

M3a review gate round 3: /meta could also expose the instance's serving limits a client needs to explain a refusal before it happens: `max_verified_clauses` (and `max_verification_candidates`, decision-010) and the query-length cap (`MAX_QUERY_LENGTH`, 2,000 code points), so the search box can warn as the user types and the record page can say by how much a withheld replay is over the limit. Additive to MetaResponse; scope it with this task or split it out.

As built (decision-011): POST /parse answers an additive required field filters: {venue, year, track, status} (null exactly when errors). venue/track/status: ParsedClause {field, negated, span, toggleable, reason, values}; year: ParsedYearClause with ranges (YearRange) instead of values. Unrestricted field: zero-width span at len(q), values = every vocabulary value (venue) or ranges [1000..9999] (year); default: its values. reason is an open enum (OPEN_ENUMS 'clause reason'): multiple_clauses, nested, mixed_fields, negated, too_long, too_deep, unparsable_edit. AC1 note: computed by query/clauses.py::filter_clauses(q, parse(q, mode)), documented in spec 02 §Filter clauses and §Outputs, not a ParseResult field: it parses the widest edited string (up to 4 extra parses, ~1 ms short / ~30 ms at 1,900 code points), which /search and replay must not pay, and parse would recurse. Cap check (TASK-039 review + M3a gate): the widest click (every vocabulary value; year one dddd..dddd range) spliced or wrapped exactly as the reducer writes it is parsed in the query's mode: PARSE_TOO_DEEP -> too_deep, PARSE_TOO_LONG (raw or canonical, decision-008) -> too_long, other errors -> unparsable_edit (trailing escape); an edit that doesn't leave exactly one top-level clause -> multiple_clauses. Goldens at depth 63/64 and 1,852/1,853 code points. A nested clause beside one top-level clause leaves the top-level one editable (spec 05 wording: only a field whose only clause is nested is blocked). Frontend: FilterClause/FilterField/ClauseReason derived from components['schemas']['ParsedClause'|'ParsedFilters']; clauseFromParse(filters[field], q, mode) -> {clause, reason}; actions carry reason; reducer maps negated -> NEGATED_CLAUSE, too_long -> TOO_LONG, too_deep -> TOO_DEEP (new code), others/unknown -> NO_EDITABLE_CLAUSE with worded reasons. Not done here: the round-3 note about /meta exposing max_verified_clauses / max_verification_candidates / MAX_QUERY_LENGTH is left for a separate task (not created: needs approval).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
POST /parse now reports each filter field's top-level clause as filters (additive; decision-011; spec 02 §Filter clauses, spec 04, spec 05). Derivation in query/clauses.py on the flattened canonical tree, with reasons for non-toggleable fields and a widest-edit parse check against PARSE_TOO_LONG/PARSE_TOO_DEEP. The reducer's FilterClause is derived from the generated ParsedClause (clauseFromParse); the local type and TODO are gone. One golden file (frontend/src/lib/filter-clause-golden.json, 18 cases: typed, default, unrestricted, canonical-pasted, astral, Scholar, OR-merged, flattened multi-clause, dedup copy, negated, nested under OR, mixed fields, depth 63/64, 1,852/1,853 code points, trailing escape) drives backend/tests/unit/test_clauses.py, backend/tests/contract/test_parse_filters.py and the reducer test; the wrap golden test also checks /parse reports the clause it wraps. Verified: uv run pytest 3593 passed 2 skipped; npm test --workspace frontend 290 passed; make lint and make tooling green.
<!-- SECTION:FINAL_SUMMARY:END -->
