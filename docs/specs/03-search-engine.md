# 03 — Search engine

Status: **draft for review** · depends on: 01 (snapshot), 02 (AST, normalize) · consumed by: 04, 06, 07

## Purpose

Given an AST from 02 and a snapshot from 01, return the **exact** matched set, ranked, with highlights and
facet counts, in well under a second. Correctness is defined by a **reference matcher**. The Tantivy index
is only an optimisation of it.

## Two engines, one contract

```python
class Engine(Protocol):
    index_version: str
    def search(self, ast, *, sort="relevance", offset=0, limit=50) -> SearchResult: ...
    def match_ids(self, ast) -> frozenset[str]            # full set, used by export and tests
    def expand(self, wildcard) -> list[str]               # term-dictionary expansion
    def facets(self, ast, fields) -> dict[str, dict[str, int]]
```

- **`ReferenceEngine`** is pure Python. It evaluates the AST directly over the normalized token lists of
  every record (positions included). It is slow (O(corpus) per query) and obviously correct. It is the
  test oracle. It never ships behind the API.
- **`TantivyEngine`** is the production engine. For any AST and snapshot,
  `TantivyEngine.match_ids == ReferenceEngine.match_ids`. That equality is a CI gate (07).

## Tokenizer

A custom Tantivy analyzer named `exact_v1`: a tokenizer that splits on non-alphanumerics → lower-case →
ASCII/diacritic folding. There is **no stemmer and no stopword filter.** The query side does not use
Tantivy's query parser. We compile our own AST. To keep the two sides from drifting, the index is fed
**pre-normalized text** from `normalize.py` (02). Tantivy then only needs to split on whitespace, so the
Rust side contains no normalization logic of its own. A test asserts that tokenizing through the index
and through `normalize.py` gives identical token streams across the whole corpus.

## Index schema

| Field | Tantivy type | Indexed | Stored | Fast |
|---|---|---|---|---|
| `id` | text (raw) | ✓ | ✓ | |
| `title` | text, positions | ✓ | ✓ | |
| `abstract` | text, positions | ✓ | ✓ | |
| `venue`, `track`, `status` | text (raw, facet) | ✓ | ✓ | ✓ |
| `year` | u64 | ✓ | ✓ | ✓ |
| `record` | JSON (authors, urls, presentation, keywords) | | ✓ | |

## AST → Tantivy compilation

| AST | Tantivy query |
|---|---|
| `Term t` (no field) | `Boolean(SHOULD title:t, SHOULD abstract:t)` |
| `Phrase` | `PhraseQuery` per field, combined with OR. Never across fields. |
| `Near(a, b, n)` | Per field: `PhraseQuery([a, b], slop=n)` OR the reversed order. Multi-token operands are handled through the reference definition, with a documented fallback: the postings are candidate-filtered by Tantivy, then verified by position in Python. |
| `Wildcard` | Expanded via the term dictionary (the FST behind `RegexQuery` / term streaming) into an explicit OR of terms. The expansion is returned to the caller. |
| `And` / `Or` / `Not` | `BooleanQuery` MUST / SHOULD / MUST_NOT |
| `Filter` | `TermQuery` or `RangeQuery` on the fast fields, applied as a non-scoring filter |

Every compiled query is also rendered as a readable string for debugging (`op search --explain`).

## Ranking (inside the matched set only, guarantee 5)

- The default `sort=relevance` is **field-weighted BM25**: per-field BM25 scores combined with boosts
  `title=2.0` and `abstract=1.0`, with k1=1.2 and b=0.75. This approximates BM25F. The spec does not claim
  it is true BM25F. The weights are configurable and recorded in `index_version`, because ranking is part
  of what gets reproduced.
- Negated and filter clauses never contribute to the score.
- Other sorts: `year_desc`, `year_asc`, `title`. The tie-breaker is always `id`, so the order is fully
  deterministic.
- `sort=semantic` is supplied by 06 when it is enabled.

## Highlights

For each hit, return the match spans per field, computed from the **AST** (not from Tantivy's snippet
generator), so what's highlighted is exactly what matched. That covers phrase spans and expanded wildcard
terms.

## Exclusion accounting (guarantee 6, PRISMA)

For every search, also compute the size of the matched set **with the default filters removed** (the
`identification_query` of 02 §Default filters), and break the difference down by filter, e.g. `{"track": {"workshop": 212, "competition": 4}, "status": {"rejected": 88}}`.
The API exposes this as `excluded` (04). It maps directly onto PRISMA's "records removed before screening".

Counting rules (so the PRISMA number is never double-counted):
- `excluded.total = |matched without default filters| − |matched with them|`.
- Buckets are assigned **in a fixed order, track first, then status**. A paper that is both a workshop
  paper and rejected counts once, under `track.workshop`. So the buckets always add up to `excluded.total`.
- Only **default** filters produce exclusions, and a default is recognised by content (02 §Default
  filters): a typed conjunct identical to a default counts as the default. Any other filter the user wrote
  (for example `year:2023..2026`, or a different `track:` set) is part of the search itself, not an
  automated removal, and is never counted in `excluded`.
- "Identified" is therefore **conditional on the user's own limits.** The defaults-removed set keeps every
  user-written filter (year, venue, …). The methods text says so (05).
- **An "include" action ends the default.** Clicking "include" on an exclusion (05 §Components 5) writes a
  non-default `track:`/`status:` set into `q`. Because a default is recognised by content, that set is no
  longer a default: it produces no `excluded` bucket, stays in the `identification_query` as a user limit,
  and the methods text changes accordingly. The UI says so in the include action's tooltip.
- **Unclassified is not ineligible.** Records removed because their `track` or `status` is `unknown` are
  itemised separately (`excluded.track.unknown`, `excluded.status.unknown`) and are never folded into
  another bucket. The UI and the methods text show them on their own line, so a review can choose to report
  them or screen them.

## Error handling

- A search whose query does not parse never reaches an engine: 02's diagnostics go back as a 422 (04 §Error
  handling). The engines only ever see a valid AST.
- A wildcard over 200 expansions is a `WILDCARD_TOO_MANY_EXPANSIONS` error from `expand`, never a silently
  truncated OR.
- An engine failure (a corrupt or missing index segment) is a typed exception mapped at the API edge to 500
  `API_INTERNAL`, or 503 `API_INDEX_NOT_LOADED` while no index is loaded. The engine never falls back to a
  partial set or to the reference engine behind the API.
- A differential mismatch in CI is a failing gate, reported with the shrunk AST; never a skipped test.

## Versioning

```
index_version = sha256( snapshot_hash, TOKENIZER_VERSION, SCHEMA_VERSION, ranking_params )[:12]
```

Indexes live at `data/indexes/<index_version>/`, are immutable, and several can be kept. The API serves one
as "current" and can load a pinned older version to replay a search record.

## Performance budgets (CI-benchmarked on the M4 corpus, about 80k docs)

- Index build: under 2 minutes. Index size: under 500 MB.
- p95 latency: under 100 ms for a search returning the first 50 hits, and under 300 ms for `match_ids`
  with exclusion accounting.
- A wildcard expansion of up to 200 terms: under 50 ms.

## Testing

- Differential testing (a CI gate): Hypothesis generates random ASTs over the corpus vocabulary (including
  rare terms, phrases, NEAR, wildcards and filters). Assert that
  `TantivyEngine.match_ids == ReferenceEngine.match_ids` on a 5k-record fixture snapshot.
- Golden fixtures from 02 run end to end through both engines.
- Determinism: the same query and `index_version` give identical order and scores.
- A tokenizer-parity test over the full corpus.
