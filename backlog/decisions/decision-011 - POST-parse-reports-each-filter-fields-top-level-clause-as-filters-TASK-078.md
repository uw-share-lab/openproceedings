---
id: decision-011
title: POST /parse reports each filter field's top-level clause as filters (TASK-078)
date: '2026-09-27 18:06'
status: accepted
---
## Context

A facet or include click rewrites `q` (guarantee 3; spec 05 §URL is state). The reducer
(`frontend/src/lib/search-state.ts`) splices a new clause over the field's one top-level clause, or wraps an
applied default as `(q) AND field:(…)`. It needs that clause's code-point span and values, and must never
re-parse filters in TypeScript (nextjs-conventions). `/parse` returned the AST and `defaults`, but deriving
the clause from them means walking OR-merged filters, NOT-wrapped clauses and flattened AND groups on the
client. `/api/v1` is frozen at its first release, so the report has to be an additive field whose shape
stays put.

Choices the shape forces:
1. **Where it lives.** (a) A field of 02's `ParseResult`, computed in `parse`. (b) A separate function in
   `query/`, `clauses.filter_clauses(q, parse(q, mode))`, that `POST /parse` serves as `filters`. Deciding
   whether a click is safe near the caps means parsing the edited string: up to four more parses per call
   (about 1 ms for a short query, about 30 ms at 1,900 code points). Under (a), `/search`, replay and `op
   search` would pay for it, and `parse` would call itself. We chose (b).
2. **Shape.** Either a list of clauses, or one object keyed by field. We chose the object
   `{venue, year, track, status}`, so a client reads `filters.track` without searching. Each value carries
   `field`, `negated`, `span`, `toggleable` and `reason`. Venue, track and status add `values` (strings);
   year adds `ranges` (`YearRange`s, as the AST's `Filter` holds them), since a year set is not a value list.
3. **A field with no clause of its own.** Either an empty list plus a flag, or the zero-width span
   `(len(q), len(q))` (where `defaults.py` inserts a default) plus the values the field admits. We chose the
   second: the default's values for track and status, every vocabulary value for venue, and `1000..9999` for
   year. The reducer then writes the clause out the same way for a default and for an unrestricted field.
4. **When a click can't be made.** A boolean alone would leave the UI unable to say why. So `toggleable:
   false` comes with a `reason`, an open enum (decision-009): `multiple_clauses`, `nested`, `mixed_fields`,
   `negated`, `too_long`, `too_deep`, `unparsable_edit`. `span` and `values` are null exactly when there is
   no single clause. A negated clause keeps its span and values, with `negated: true`.

## Decision

`POST /api/v1/parse` answers an additional required field, `filters: ParsedFilters | null` (null exactly
when `errors` is non-empty). It is computed by `openproceedings.query.clauses.filter_clauses`, not by
`parse`, and not in the router. "Top-level" is judged on the flattened canonical tree, the one
`defaults.py` reads. A field is toggleable only when it has exactly one top-level clause, written as one
top-level conjunct, that is positive (or it has no clause at all, so the wrap applies). The widest edit a
click can make must also parse in the query's mode, and leave exactly that one top-level clause: every
vocabulary value, or one `dddd..dddd` year range. If it doesn't, the clause is not toggleable, with
`too_long` (decision-008's raw or canonical cap), `too_deep` (PARSE_TOO_DEEP) or `unparsable_edit`. A field
whose only clauses are nested is not toggleable. A nested clause beside a top-level one leaves the
top-level one editable, and the nested one stays applied (decision-001's facet rule).

## Consequences

- Additive within v1: a new required response field, the component schemas `ParsedFilters`,
  `ParsedClause` and `ParsedYearClause`, and a new open enum `clause reason` in `api/openapi.py`. No existing
  field, canonical string, `canonical_hash`, `QUERY_VERSION` or `index_version` changes, and no stored
  record replays differently.
- Spec 02 §Filter clauses states the rules, spec 04 the `/parse` row, spec 05 how the reducer uses them.
  The frontend's `FilterClause` is derived from the generated `ParsedClause` (`clauseFromParse`), and the
  reducer words each reason (`TOO_DEEP` is a new reducer code).
- One golden file, `frontend/src/lib/filter-clause-golden.json`, drives `backend/tests/unit/test_clauses.py`,
  `backend/tests/contract/test_parse_filters.py` and the reducer's test. The server's report and the
  client's splice can't drift apart without a red test.
- Being conservative near the caps has a cost: the check uses the widest edit, not the value clicked. A
  query within about 100 code points of the cap can have a toggle disabled that a single-value click would
  have fit. Revisit if usability testing shows it matters (per-value reporting would be additive).
- A click always writes the grouped form, `field:(v)` even for one value (m3-followups gate, query-semantics
  review): a bare `field:v` spliced before a group touched it (`trust track:(main OR workshop)(x OR y)` →
  `trust track:workshop(x OR y)`, `PARSE_PAREN_TOUCHES_WORD`, a 422 after a toggle `/parse` had allowed). With
  every edit ending in the clause's `)`, the widest-edit check covers every edit shape; a property test
  applies every single-value toggle and include to generated queries. The canonical form and hash are
  unchanged (`field:(v)` canonicalises to `field:v`).
- The `nested` rule is conservative for `track` and `status`. When a field's only clauses are nested (`x
  (track:workshop OR y)`), the default is still applied, yet the field is reported `nested` and not
  toggleable, so the banner's include button is disabled exactly when the default removes papers. The
  zero-width wrap `(q) AND track:(…)` would work there: the review's fuzz found about 2,900 such cases among
  its generated queries. Kept for now (it never offers an edit that could fail or mislead, and the query
  text stays editable); it can be relaxed later by reporting the zero-width span for a field whose default
  applies despite a nested clause, which would be additive (a `nested` report becoming toggleable).
- Revisit when a filter field is added (it gets a key in `ParsedFilters`, which is additive) or when year
  gets a UI control (its widest edit would then need to match what that control writes).

