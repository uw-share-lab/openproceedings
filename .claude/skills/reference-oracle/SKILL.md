---
name: reference-oracle
description: What ReferenceEngine is and why it must stay naive — it defines correct matching (guarantee 1), shares no compile path with Tantivy, evaluates every AST node directly over normalized token positions (terms, phrases, NEAR, wildcards, filters, NOT), and never ships behind the API. Use when writing or reviewing engine/reference.py, deciding what a node "should" match, or judging whether a differential test still compares two independent implementations.
---

# The reference oracle (spec 03 §Two engines, one contract)

`backend/src/openproceedings/engine/reference.py::ReferenceEngine` is the **definition** of what a query
matches. `TantivyEngine` is only an optimisation of it. The CI gate `TantivyEngine.match_ids ==
ReferenceEngine.match_ids` is only worth something if the two are independent.

## Independence rules (each violation is a Must)
- Imports allowed: `query/ast.py`, `query/normalize.py`, the snapshot loader, the stdlib. **Never**
  `tantivy`, `engine/compile.py`, `engine/tantivy_engine.py`, `engine/rank.py`, or a helper shared with them.
- No indexes, caches, precomputed postings or "optimisations". O(corpus) per query is the design. The
  5k-record fixture keeps it fast enough.
- Its wildcard vocabulary is built from the snapshot's normalized tokens, not read from Tantivy's term
  dictionary.
- It is never mounted behind the API. `openproceedings.api` must not import `engine.reference`. Keep a test
  that asserts it. CLI access (`op search --engine reference`) is for debugging and review only.
- Readability beats cleverness. Each node's evaluation should be a few lines a reviewer can check against
  spec 02 by eye.

## Evaluation semantics
Per record, `tokens[f]` = `normalize(record[f])` for `f ∈ {title, abstract}` (list index = position). The
universe `U` = all record ids in the snapshot.

| Node | Matches record when |
|---|---|
| `Term t` (field f, or title∪abstract if unfielded) | `t in tokens[f]` for some searched f |
| multi-token term / `Phrase [p0..pk]` | some f and i with `tokens[f][i:i+k+1] == [p0..pk]`, **within one field** |
| `Near(a, b, n)` | some f with occurrences of a and b as non-overlapping spans in that field, either order, with ≤ n tokens strictly between the spans |
| `Wildcard` | any expansion (`.claude/skills/wildcards-and-expansion/SKILL.md`) matches as a `Term` |
| `And` / `Or` | set intersection / union |
| `Not x` | `U − eval(x)`, so `a OR NOT b` is well-defined |
| `Filter venue/track/status` | exact equality with the record's value (`venue` compared case-insensitively) |
| `Filter year a..b` | `a ≤ year ≤ b`, inclusive |

The oracle does **not** add default filters. They are already explicit in the AST
(`.claude/skills/default-filters/SKILL.md`). It computes exclusion counts by evaluating the AST with the
added default clauses removed, the same way the engine does.

## Contract surface
It implements the same `Engine` protocol: `match_ids`, `expand`, `facets`, and a `search` whose order is
`id` only. The oracle does not rank, and ranking never changes membership anyway.

## As built (task-016)
- `backend/src/openproceedings/engine/reference.py`; the protocol and `Searchable` record shape are in
  `engine/protocol.py` (types only, so sharing it shares no logic).
- `tests/unit/test_reference.py` has one row per rule above, plus import-isolation tests (the oracle's
  allowed imports; `api/` never imports it). `tests/golden/test_reference_200.py` runs 44 queries over a
  200-record fixture whose expected sets come from an independent evaluator
  (`tests/fixtures/corpus/make_reference_200.py`), and a property that canonical form never changes a match set.
- Every wildcard in a query (phrase items and NEAR operands too) is expanded once, before any record is
  evaluated, so the 200 cap never depends on which records are reached (and a 5k differential run stays
  O(corpus)). An empty snapshot expands nothing and matches nothing.
- Facets judge "top-level" after flattening nested ANDs, as on the canonical tree. `track`/`status`
  compare exactly; `venue` case-insensitively.
- Exclusion accounting (`excluded`) is task-026; it evaluates `ParseResult.identification_ast`.

## When the two disagree
Assume the Tantivy side is wrong until the oracle is shown to contradict spec 02 or 03. If the oracle is
wrong, fix it in its own reviewed change, with a golden case quoting the spec sentence. Never "fix" it to
match Tantivy's output.
