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

A custom Tantivy analyzer named `exact_v1` that **only splits on whitespace**. It does no lower-casing
beyond a no-op, **no ASCII or diacritic folding** (that would turn `ørsted` into `orsted`, which the token
contract keeps distinct), no stemmer and no stopword filter. The query side does not use
Tantivy's query parser. We compile our own AST. To keep the two sides from drifting, the index is fed
**pre-normalized text** from `normalize.py` (02). Tantivy then only needs to split on whitespace, so the
Rust side contains no normalization logic of its own. A test asserts that tokenizing through the index
and through `normalize.py` agrees across the whole corpus (the stored text, the positions by phrase
read-back, and every term's document frequency; see the as-built note below for what that does not cover). Tantivy silently drops
a token over 65,530 UTF-8 bytes, so the build refuses a record with one rather than index less than the
reference engine matches (`engine/index.py`, `op index build`).

As built (task-029, `engine/parity.py`, `op index parity`): record by record, in id order, against
`normalize()` of the snapshot's raw text:
- the stored field through `exact_v1` gives the same tokens (the text round-trips);
- the positions Tantivy indexed are read back with a phrase query over each field of 2+ tokens,
  restricted to the record;
- each term's document frequency in the term dictionary matches, in both directions.

Term frequencies are checked only as far as the phrase read-back implies. The first difference fails,
naming the record, field and token (or the term). That message quotes tokens: it is local terminal output,
never logged. It runs on the synthetic 5k corpus in CI; on the real corpus it runs locally (decision-004).

## Index schema

| Field | Tantivy type | Indexed | Stored | Fast |
|---|---|---|---|---|
| `id` | text (raw) | ✓ | ✓ | |
| `title` | text, positions | ✓ | ✓ | |
| `abstract` | text, positions | ✓ | ✓ | |
| `venue`, `track`, `status` | text (raw, facet) | ✓ | ✓ | ✓ |
| `year` | u64 | ✓ | ✓ | ✓ |
| `ord` | u64: the record's position in id order (`ids.txt` maps it back) | ✓ from schema 3 | | ✓ |
| `title_rank` | u64: the record's position in display-title order (`sort=title`) | | | ✓ |
| `record` | bytes: compact JSON of the display fields (original title and abstract, authors, urls, presentation, keywords, venue_id_raw); stored, never indexed (a JSON field would be) | | ✓ | |

## AST → Tantivy compilation

| AST | Tantivy query |
|---|---|
| `Term t` (no field) | `Boolean(SHOULD title:t, SHOULD abstract:t)` |
| `Phrase` | `PhraseQuery` per field, combined with OR. Never across fields. |
| `Near(a, b, n)` | Two different single terms: per field, `PhraseQuery([a, b], slop=n)` OR the reversed order (exact on tantivy 0.26.2, measured). A phrase or wildcard operand, a term with itself, or a phrase with a wildcard item takes the documented fallback: candidates filtered by Tantivy, then verified by position in Python over the stored token streams; the clause then matches its candidate query narrowed by an id set, naming the verified ids or, when fewer, the candidates that failed (excluded): the same matches and scores either way, and Tantivy resolves the shorter list on each search (TASK-076). |
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
- `sort=semantic` is supplied by 06 when it is enabled. 06 is deferred to phase 2 (decision-017), so v1
  has only the four sorts above and refuses `sort=semantic` with 422 `API_BAD_PARAM` (the CLI rejects it as
  a usage error).
- As built (task-025, `engine/tantivy_engine.py`): the weights are per-field boosts; k1 and b are
  Tantivy's fixed constants, checked against a hand-computed score; the whole match set is ordered by the
  sort's key with `id` last (never Tantivy's hit order), then paged; the sort definitions are part of
  `ranking_params`. Every Boolean is compiled as a balanced binary tree, so identical texts get identical
  scores whatever the index layout (a flat union of three or more clauses leaves them an ulp apart).
  The engine refuses an index built with another schema, tokenizer or Tantivy version, or other bm25 params.

## Highlights

For each hit, return the match spans per field, computed from the **AST** (not from Tantivy's snippet
generator), so what's highlighted is exactly what matched. That covers phrase spans and expanded wildcard
terms.

As built (task-027, `engine/highlight.py`): `highlights(ast, record, expansions)` evaluates the AST on one
record over `tokenize`'s offset map. A term or expanded wildcard term lights each token it matches; a phrase
lights one span per occurrence; NEAR lights the operand occurrences that form a pair within the distance;
AND lights its children, OR only the children that matched; NOT and filters light nothing. A node that
doesn't match has no spans, so a branch that didn't match lights nothing. Overlapping spans merge. A LaTeX
math command's span is its name without the backslash (`$\alpha$` lights `alpha`); markup that opens a word
(an accent macro, `\-`, or a math `^`/`_`) is part of the word (`\"{O}del` and `$^2x$` light all of it; task-074). Two tokens' spans overlap only on exactly one code point that folds
to several pieces (`½`), never on a combining slash's marks (task-075). The highlighter's verdict
is checked against ReferenceEngine on every fixture record for all 44 golden queries.
A NEAR over a long field is a binary search per occurrence, never a check of every pair. A hit the
highlighter doesn't match raises `EngineInternalError`.

Cost, as built (task-073): the task-027 review measured ~174 ms to highlight a 50-hit page of ~400-word
abstracts, almost all of it `tokenize`, over the 100 ms page budget. A page now builds one `Highlighter` for
its query (`search.run`), which works out each leaf's allowed tokens once; per hit, each field is tokenized
once and only if some leaf reads it, and a leaf's occurrences come from a map of where each token stands.
`tokenize` got two exact fast paths (a whole text that is ASCII with no `\` or `$`; an ASCII character with
no mark after it), with no `TOKENIZER_VERSION` bump: both are pinned to a frozen copy of the old loop, and
the highlighter to a frozen copy of the old one, span for span (`tests/unit/engine/test_highlight_speed.py`).
TASK-088 made the loop, which every other text takes (one with a non-ASCII character, a `\` or a `$`),
faster in three exact ways, again with no bump: a text with no `\` and no `$` skips the LaTeX mask (it would
be all KEEP); a stretch of ASCII characters with no markup in it and no mark after it is taken word by word
from a regular expression instead of character by character; and a raw character whose fold doesn't
depend on the letter before it (nearly all of them: the fold is compared after one base of each class the
mark rule tells apart) is folded once per process, in a bounded table. The loop and its `Tail` are pinned to
a frozen copy of the loop before it (`tests/unit/tokenize_before_088.py`).
Nothing is precomputed at build and nothing is cached across requests but that table of character folds
(`_FOLDED`, a pure function of the character, holding no record or query). Measured in
`docs/results/2026-09-27-highlights.md`: highlighting a 50-hit page costs about 5–7× less (real local corpus,
5k fixture, synthetic 80k), and a 50-hit search with its display records and highlights is inside the 100 ms
budget at 80k (exclusion accounting keeps its own 300 ms budget). The `/search` endpoint as a whole (with
exclusion accounting and facets) is too, in wall time, since its facets overlap the page: see §Performance
budgets. It is a row of the `bench` workflow
(`test_search_first_50_hits_with_highlights`) and a column of the 80k report.

## Exclusion accounting (guarantee 6, PRISMA)

For every search, also compute the size of the matched set **with the default filters removed**
(`ParseResult.identification_ast` of 02 §Default filters; the string form, `identification_query`, can be
`""` or all-negative, so counts never re-parse it), and break the difference down by filter, e.g. `{"total": 304, "track": {"workshop": 212, "competition": 4, "unknown": 0}, "status": {"rejected": 88, "unknown": 0}}` (the shape pinned in 04).
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
- As built (task-026, `engine/exclusions.py`): `excluded(engine, parsed, total)` uses only the Engine protocol,
  so both engines compute it the same way. The track buckets are the track facet of `identification ∧
  track-default` (the facet drops that clause, so it counts every identified record). The status buckets
  are the status facet of the effective query (every identified record that passed the track default).
  `|identified|` is the first default's facet total, and `total` is the search's own count, passed in, so
  the query runs no third time (no default applied: 0, with no evaluation). Buckets that don't sum to
  `|identified| − total` are an `EngineInternalError` (`API_INTERNAL`, a 5xx), never a silent report. Tested against a brute-force count on the 200-record fixture,
  for both engines, including an `identification_query` of `""` and an all-negative one. A search that
  shows facets reads both buckets from the facet combos it already collected; one that doesn't (`op search`,
  a record's save or replay) aggregates only track and status (`TantivyEngine.facets(over=…)`; TASK-166), so
  it reads a few dozen combos rather than hundreds. The counts are the same (`test_facets_equal.py`).

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

As built (TASK-167, SCHEMA_VERSION 3): new indexes index `ord`, and a position-verified clause names its ids
as a u64 term set on `ord` rather than on the text `id`. The code serves both schemas: `index.SERVED_SCHEMAS`
maps each served `schema_version` to its `SchemaForm`, and an index takes the form its manifest names. A
schema-2 index keeps the text-`id` path, so a record pinned to one still replays `reproduced` on it (guarantee
4). Records saved by the pre-change code on the real M4 index replayed 10/10 `reproduced`, and a contract test
checks the same through the API. Every query gets the same ids and the same float scores on either schema:
the differential suite, the Trust-Evals strings in every sort, and each verified clause's form.

Measured (`docs/results/2026-10-02-exclusions-and-verified-forms.md`, old and new alternated, load 30–155):

| Measurement | Schema 2 | Schema 3 |
|---|---|---|
| `"AI agent$"` id set alone (20,752 ids, synthetic 80k), CPU median | 11.3 ms | 6.2 ms |
| `main-2-pop` warm search, synthetic 80k, CPU p50 | 29.4 ms | 29.7 ms |
| `main-2-pop` warm search, real M4 corpus, CPU p50 | 26.4 ms | 25.6 ms (no measurable gain under load) |

These overloaded measurements show no measurable end-to-end gain. The isolated claim is historical;
`tests.bench.id_sets` now separates construction and collection, including lazy lookup first-use and memory
(`docs/results/2026-10-02-perf-recovery.md`). Inside a search, the id set is one MUST clause of an intersection that the rarer
clauses drive, so most of its isolated cost (TASK-076's "about 10 ms a search") never reaches a search. The
change was kept by owner decision, since it is exact and replay-safe (decision-030).

Schema 2 is retired, and dropped from `SERVED_SCHEMAS` with its path and tests, only once no search record pins
a schema-2 index. The order is: rebuild every served index at schema 3, repoint `current`, then `op index
retire` each schema-2 version, which `op index retire` refuses while a record pins it. Any other schema is
refused (`unservable`).

**Served tokenizers (decision-031).** An index's terms are its tokenizer's, so a query is parsed, its canonical
hashed and its hits highlighted with the tokenizer its index was built with (`TantivyEngine.tokenizer_version`,
from the manifest). This code serves the current `TOKENIZER_VERSION` ("3", which new indexes are built with) and
the one before it ("2"): `normalize.SERVED_TOKENIZERS`, each a `TokenizerForm` that code branches on. An index
built with any other tokenizer is `tokenizer_version_mismatch` (unservable). A search record pinned to a
tokenizer-2 index therefore replays `reproduced` on it after the bump; on a tokenizer-3 index it is `drifted` in
`tokenizer_version`. The impact on the real corpus, and the replay check against the real index, are in
`docs/results/2026-10-02-tokenizer-3.md`. Retiring version 2 follows the index-versioning skill.

## Performance budgets (for the M4 corpus, about 80k docs; CI benchmarks the 5k fixture and nightly reports a synthetic 80k, 07 §E)

- Index build: under 2 minutes. Index size: under 500 MB.
- p95 latency: under 100 ms for a search returning the first 50 hits, and under 300 ms for `match_ids`
  with exclusion accounting.
- A wildcard expansion of up to 200 terms: under 50 ms.
- **Exception, as built (task-024):** a clause that takes the position-verified fallback (a phrase with a
  wildcard item; NEAR with a phrase or wildcard operand, or a term with itself) costs time linear in its
  candidates' text and can exceed the search and `match_ids` budgets when cold: on a synthetic 80k corpus,
  stopword cases such as `the NEAR/5 the` take 2.3–3.3 s cold, and the wildcard-phrase protocol string
  `main-2-pop` 10.1 s to search and 10.5 s for `match_ids` + exclusions (`docs/results/2026-09-27-bench.md`). It is never capped, because a cap would make
  a query's result depend on the corpus's size and break replaying search records; task-031 measures these
  cases, and an engine caches each verified clause, so facets and repeats don't pay again.
- Measured (task-031, `docs/results/2026-09-27-bench.md`, a synthetic 80k corpus, quiet machine): build 30 s,
  99 MB, 391 MB peak in the largest single process. Every Trust-Evals string's search and `match_ids` +
  exclusions is within budget, except `main-2-pop` (wildcard phrases) when cold: 10.1 s to search and 10.5 s
  for `match_ids` + exclusions, the exception above. Warm (the engine's verified-clause cache and compiled-
  query memo), its search is 27 ms p95 over 200 runs.
- Measured, warm searches over wildcard phrases (TASK-076, `docs/results/2026-10-02-wildcard-phrases.md`; no
  other test run, load 4–11). Tantivy resolves a verified clause's id set on every search (0.5–1.3 µs an id), so a clause names
  the shorter list: its verified ids, or the candidates that failed, excluded (§AST → Tantivy compilation, the `Near` row).
  `report_80k` (`docs/results/2026-10-02-bench.md`): `main-2-pop` warm **p95 28.8 ms, p99 48.0 ms** over 200
  runs on the synthetic 80k. On the real M4 corpus its warm search went from p95 46.8 ms to 27.3 ms (old and new
  compile alternated, 200 rounds each; `tests/bench/warm_verified.py`); no other string changed.
- Measured, the `/search` endpoint (M3a review gate; `search.run(limit=50, facets=True, highlight=True)`,
  synthetic 80k). A first page collects the text query twice: the page, and once without its top-level
  filters for every facet and both exclusion buckets (task-086: counts per (venue, year, track, status) from
  one nested terms aggregation, the rest in Python; memoised per base in `TantivyEngine.faceted`). Two
  collections are the floor of an exact design (the page needs the effective query's own scores), so the
  second runs on a worker thread, overlapping the first (M3a review gate round 2): `search.run` compiles the
  effective tree in the request's thread (a cold verified clause takes its one verification slot there, and
  the request keeps the ids it verified in its own `Scope`, so no later compile of it, the worker's
  included, verifies a clause again however the memos are trimmed; the worker never verifies: round 3),
  then starts the facet aggregation on a worker and collects, reads and highlights the page meanwhile
  (Tantivy releases the GIL while collecting). The result is the sequential one, field for field
  (`tests/unit/test_search_overlap.py`). **First page, wall p95 over 200 runs: 57–85 ms for every non-empty
  Trust-Evals string, within budget** (`main-1` 84.5 ms, `main-3-sources` 76.8 ms; sequentially 76–116 ms,
  interleaved in the same run); a later page 54–77 ms. CPU per request is unchanged, 74–109 ms: the overlap
  saves wait, not work, so throughput under load is as before (`docs/results/2026-09-27-search-overlap.md`,
  load 6–14). Where `main-1`'s first page goes (median CPU, task-088's breakdown): the page's collection
  34 ms, the facet collection 37 ms (now overlapped), highlighting 50 hits 33 ms (the tokenizer's slow path:
  the synthetic text is about half non-ASCII, real abstracts about a quarter), counting 3 ms, display 1 ms.
  `report_80k` reports both pages as wall p95 over 200 runs, and the first page's CPU per request.
- Measured, the `/search` endpoint after TASK-088's tokenizer work (`docs/results/2026-10-01-tokenizer-fast-path.md`,
  made with `tests/bench/alternate.py`; load 4–8, no other test run). Old and new tokenizer alternated round by
  round in one process, 200 rounds each: median first-page CPU 0.6–8.1 ms lower on the real M4 corpus (index
  `05a0541717f6`, 95,877 records; `main-1` 35.5 → 27.4 ms) and 11.5–12.7 ms lower on the synthetic 80k
  (`main-1` 104.4 → 92.2 ms); new first-page wall p95 3.0–70.5 ms (real) and 44.8–64.4 ms (synthetic).
  `report_80k`'s `/search` columns on the real corpus, new code: **first page, wall p95 2.9–73.4 ms for every
  Trust-Evals string, within budget** (`main-2-pop` 73.4 ms, the rest under 46 ms), a later page 1.4–64.6 ms,
  CPU per request 3.2–112.5 ms. The real corpus matches far fewer records per string than the synthetic one
  (50 for `main-1`, 88 for `main-2-pop`), and `main-2-pop`'s cost there is mostly collecting its page and its
  facets, not highlighting (task-076). The tokenizer alone takes 74% of its old CPU over real titles and
  abstracts (56% over those that leave the whole-text ASCII path) and 59% over the synthetic ones.
- Each hit's `abstract_source` (TASK-134, decision-018) costs the request a dict lookup per hit and one small
  response object: `RecordFile` computes every record's attribution once, in the load pass it already makes
  over the snapshot (spec 04 §SearchResponse). Measured on the served snapshot (1,805 records): about 95 µs
  per 50-hit page, no file I/O, and about 230 bytes of memory per record (about 18 MB at 80k); the load pass
  took 0.06 s in all. No index or `index_version` change. The `bench` workflow's `/search` rows include it.

## Testing

- Differential testing (a CI gate): Hypothesis generates random ASTs over the corpus vocabulary (including
  rare terms, phrases, NEAR, wildcards and filters). Assert that
  `TantivyEngine.match_ids == ReferenceEngine.match_ids` on a synthetic 5k-record fixture snapshot, plus 20
  records at the 200-expansion cap's edge (decision-004; 07 §A).
- Golden fixtures from 02 run end to end through both engines.
- Determinism: the same query and `index_version` give identical order and scores.
- A tokenizer-parity test over the full corpus.
