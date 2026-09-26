---
id: decision-001
title: Query-language semantics settled before the lexer (task-001)
date: '2026-09-26 01:49'
status: accepted
---
## Context

Spec 02 left six query-language questions open (task-001), and the lexer (task-011) and parser (task-012)
need them settled. The Trust-Evals protocol's own search strings use a wildcard inside a phrase
(`"large language model$"`), so any rule that forbade that would break the review's queries.

## Decision

1. **`$` has the same 3-character minimum stem as `*`.** One rule for both wildcards; short stems
   (`a$`) would expand to hundreds of terms.
2. **A wildcard inside a phrase is allowed and expanded per position.** `"large language model$"` matches
   the phrase with `model` or `models` in the last position. The 200-expansion cap applies to each wildcard.
3. **A wildcard stem that normalises to several tokens becomes a phrase whose last token carries the
   wildcard.** `gpt-4*` means `"gpt 4*"`. The 3-character minimum counts the letters and digits of the
   whole stem after normalisation; the 200-expansion cap applies to the last token's expansions.
4. **Only top-level AND conjuncts suppress a default filter** (already decided; spec 02 §Default
   filters; `WARN_NESTED_FILTER`).
5. **Canonical filter order:** `venue`, `year`, `track`, `status`, then any other field alphabetically.
   The values inside an OR group of one field are sorted, so the same filter always hashes the same.
6. **Disjunctive facets remove only top-level filter conjuncts of the facet's own field.** A filter
   nested under an OR stays part of the query when that field's facet is counted, which matches rule 4.

## Consequences

- The lexer emits wildcard terms inside phrases, and the AST allows `Phrase` elements to be wildcard
  terms. `ReferenceEngine` and the Tantivy compiler expand per position (task-016, task-024).
- Golden cases for rules 1–3 and 5 land with the lexer, parser and canonical form (task-011 to task-013);
  rule 6's contract test lands with the API (task-035).
- Spec 02 §Grammar and §Outputs, and spec 04 §SearchResponse (facets), state these rules.
- Reversing any rule after M1 changes query meaning: a `query_version` bump.
