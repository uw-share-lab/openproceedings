# The tokenizer loop's fast paths, and `/search` on the real corpus (2026-10-01, TASK-088)

Spec 03 §Performance budgets: the first 50 hits, p95 under 100 ms. After the M3a review gate every Trust-Evals
string's `/search` first page was under budget in wall time on the synthetic 80k corpus, but its CPU per
request (what bounds throughput) was unchanged at 74–109 ms, and a third of it on `main-1` was highlighting,
almost all of that `query/normalize.py`'s per-character loop (task-088). This records the loop's new fast
paths, the proof that no token changed, and `/search` re-measured on the real M4 corpus, with the method, so
it can be rerun.

- Machine: macOS-15.6.1-arm64, 8 CPUs; Python 3.12.9, tantivy 0.26.2; code: `05eff53` plus this change.
- Indexes: the real M4 corpus, index `05a0541717f6` (95,877 records), opened read-only in the main checkout's
  `data/indexes/`; the synthetic 80k corpus (`tests/fixtures/corpus/synthetic_5k.records(80_000, (120, 250))`),
  built in a scratch directory, never under `data/`.
- **Not a quiet machine, but no other test run.** Other agents were active; before each timed run no
  `pytest` or mutation process was running anywhere on the machine, and the remaining load came from outside
  openproceedings (Spotlight indexing, a browser). The 1-minute load average was 15–31 across the runs. Old
  and new code alternate round by round in one process (the order flipping each round), so load weighs on
  both alike: read the differences with more confidence than the absolute times.

## What changed
All in `_tokenize_each_char`, the loop every text takes unless it is ASCII with no `\` or `$` (task-073's
whole-text path). Each is the same steps the loop took one character at a time, done in fewer Python steps:
- A text with no `\` and no `$` skips `_latex_mask`: math and commands need one of the two, so the mask would
  be all KEEP.
- A stretch of ASCII characters that are all KEEP, with no combining mark after its last, is taken word by
  word with `[A-Za-z0-9]+` (a regular expression search finds where the stretch ends, in the text and, for a
  text with markup, in the mask as bytes): each word appends to the open word or, when a separator follows it
  in the stretch, is a token at once; each run of separators closes the open word and joins the `Tail`.
  `close()` skips NFC and the marks-only test for an ASCII word.
- `_fold_char(c, base)` folds a raw character once per process when its fold doesn't depend on `base`.
  `_fold` reads `base` only through `_folds_marks`, which tells apart five classes of base (none, or a
  letter whose marks all fold; Cyrillic, which keeps the breve; Arabic, which keeps hamza; any other script,
  which keeps every mark), so a character whose `_fold` is the same after one base of each (`_BASES`) is the
  same after any base. The table (`_FOLDED`) is bounded at 4,096 characters.

`TOKENIZER_VERSION` stays `2`; no index is rebuilt.

## Proof that no token changed
- `tests/unit/tokenize_before_088.py` is a frozen copy of the loop at `05eff53` (TASK-067's linear runs of
  marks included). `test_highlight_speed.py` holds the loop and `tokenize_with_tail` to it, tokens (text,
  span, `op`) and `Tail`, on arbitrary, ASCII, LaTeX-heavy, combining-mark and Latin-with-typography text
  (a new strategy) and on every text of the fixture and 5k corpora; task-073's oracle,
  `tests/unit/tokenize_before.py`, still holds `tokenize` too.
- `test_a_cached_fold_is_the_fold_after_any_base` checks `_fold_char` against `_fold` for any character
  after any base (Hypothesis). Once, by hand: every code point whose fold is the same after `_BASES` (1,110,698
  of them) and has a mark in its decomposition gave the same fold after a base of each of 5,759 Unicode name
  prefixes (no exception). `OP_EXHAUSTIVE=1 tests/unit/test_normalize_exhaustive.py` (every code point in 8
  contexts against the whole-string definition) passed.
- Hand mutants of the new code: dropping the `Tail` reset, the span's markup start, the `k -= 1` before a mark,
  the NFC, the stretch's base reset, or caching a base-dependent fold each fail a test. Two survive and are
  equivalent: the marks-only test skipped for ASCII words, and an ASCII letter as the base after a stretch
  (it is in the same class as no base).
- Every `/search` timed below compared the old and new tokenizer's whole `Search` result (hits, scores,
  highlights, facets, exclusions) with `==` before timing.

## The tokenizer alone: 3,000 records' titles and abstracts, 10 rounds, interleaved, CPU time (median)

| Corpus | Texts | Old | New | Ratio |
|---|---|---|---|---|
| real M4, every text | 6,000 | 987 ms | 737 ms | 75% |
| real M4, texts off the whole-text ASCII path | 1,083 | 594 ms | 336 ms | 57% |
| synthetic 80k, every text | 6,000 | 1,766 ms | 1,064 ms | 60% |
| synthetic 80k, texts off the whole-text ASCII path | 3,132 | 1,723 ms | 1,032 ms | 60% |

On the real corpus 18% of texts leave the whole-text path, two thirds of them for a `$` or `\` (LaTeX) and the
rest for a non-ASCII character (most often `’`, `—`, `–`, curly quotes, `×`, accented letters).

## `/search` first page: old vs new tokenizer, 200 rounds each, interleaved

`test_bench.search_endpoint` (`search.run(limit=50, facets=True, highlight=True)`, the facet memo cleared
each round, as a query's first page pays). Wall time is what a client waits; CPU (process time, every thread)
is what bounds throughput.

Real M4 corpus (load 27.4 at the start, 16.2 at the end):

| String | Matches | Wall p50: old | new | Wall p95: old | new | CPU p50: old | new | CPU p95: old | new |
|---|---|---|---|---|---|---|---|---|---|
| main-1 | 50 | 30.5 ms | 22.5 ms | 31.5 ms | 23.7 ms | 35.5 ms | 27.5 ms | 36.3 ms | 28.3 ms |
| main-2-pop | 88 | 71.0 ms | 64.8 ms | 81.2 ms | 75.0 ms | 118.1 ms | 111.9 ms | 130.5 ms | 125.3 ms |
| main-3-sources | 50 | 31.2 ms | 23.3 ms | 54.9 ms | 31.1 ms | 36.2 ms | 28.2 ms | 42.0 ms | 31.9 ms |
| main-4-sources | 27 | 17.7 ms | 13.3 ms | 27.6 ms | 21.2 ms | 21.0 ms | 16.6 ms | 24.8 ms | 19.4 ms |
| main-5-sources | 21 | 13.6 ms | 10.9 ms | 17.6 ms | 12.8 ms | 16.6 ms | 13.9 ms | 18.7 ms | 15.3 ms |
| main-6-sources | 27 | 15.7 ms | 12.4 ms | 17.1 ms | 13.2 ms | 18.7 ms | 15.4 ms | 20.0 ms | 16.3 ms |
| main-7-most-updated | 27 | 15.8 ms | 12.5 ms | 16.7 ms | 13.3 ms | 18.8 ms | 15.5 ms | 19.7 ms | 16.3 ms |
| narrow | 27 | 17.0 ms | 12.7 ms | 18.2 ms | 13.6 ms | 20.1 ms | 15.8 ms | 21.2 ms | 16.6 ms |
| human-centered | 4 | 3.3 ms | 2.7 ms | 3.8 ms | 3.0 ms | 4.0 ms | 3.4 ms | 4.5 ms | 3.9 ms |
| llm-as-judge | 15 | 9.6 ms | 6.9 ms | 10.0 ms | 7.3 ms | 10.6 ms | 7.9 ms | 11.0 ms | 8.4 ms |

Synthetic 80k corpus (load 15.3 at the start, 31.4 at the end):

| String | Wall p50: old | new | Wall p95: old | new | CPU p50: old | new | CPU p95: old | new |
|---|---|---|---|---|---|---|---|---|
| main-1 | 71.2 ms | 59.1 ms | 84.9 ms | 61.7 ms | 104.6 ms | 92.6 ms | 107.7 ms | 95.4 ms |
| main-2-pop | 69.7 ms | 57.6 ms | 76.1 ms | 70.6 ms | 99.0 ms | 86.9 ms | 109.0 ms | 96.1 ms |
| main-3-sources | 71.9 ms | 59.8 ms | 84.8 ms | 74.9 ms | 105.4 ms | 93.3 ms | 108.0 ms | 96.4 ms |
| main-4-sources | 59.5 ms | 48.2 ms | 61.8 ms | 49.3 ms | 83.6 ms | 72.2 ms | 84.9 ms | 73.5 ms |
| main-5-sources | 59.5 ms | 47.9 ms | 62.8 ms | 49.6 ms | 83.0 ms | 71.4 ms | 85.2 ms | 73.0 ms |
| main-6-sources | 56.7 ms | 43.8 ms | 80.6 ms | 50.3 ms | 74.3 ms | 61.8 ms | 78.3 ms | 65.6 ms |
| main-7-most-updated | 59.2 ms | 45.9 ms | 83.6 ms | 57.3 ms | 76.4 ms | 63.5 ms | 81.1 ms | 67.1 ms |
| narrow | 67.8 ms | 54.8 ms | 134.7 ms | 99.4 ms | 90.2 ms | 77.6 ms | 95.6 ms | 83.3 ms |
| human-centered | 63.3 ms | 50.6 ms | 85.7 ms | 70.8 ms | 87.7 ms | 75.1 ms | 94.3 ms | 80.0 ms |
| llm-as-judge | 0.9 ms | 0.9 ms | 1.0 ms | 1.0 ms | 1.3 ms | 1.3 ms | 1.5 ms | 1.5 ms |

The median first page costs 11–13 ms less CPU on the synthetic corpus for every non-empty string, and 0.6–8 ms
less on the real one (fewer matches there, and fewer of their texts leave the whole-text path). `narrow`'s
synthetic wall p95 (99.4 ms new, 134.7 ms old) is load: its p50 is 54.8 ms and its CPU p95 83.3 ms.

## `report_80k`'s `/search` columns on the real M4 corpus (new code only)

`report_80k`'s own functions (`timed`, `cpu_timed`, `p95`, `ENDPOINT_ROUNDS` = 200) over the real index:
first page with the facet memo cleared, a later page (offset 50) with it warm, both wall p95, and the first
page's mean CPU per request. Load 21.3 at the start, 22.2 at the end.

| String | Matches | `/search`, first page: p95 wall | a later page: p95 wall | first page: CPU per request |
|---|---|---|---|---|
| main-1 | 50 | 24.8 ms | 6.4 ms | 28.3 ms |
| main-2-pop | 88 | 74.8 ms | 61.6 ms | 112.3 ms |
| main-3-sources | 50 | 24.0 ms | 6.7 ms | 28.1 ms |
| main-4-sources | 27 | 13.5 ms | 4.4 ms | 16.3 ms |
| main-5-sources | 21 | 11.8 ms | 4.2 ms | 14.0 ms |
| main-6-sources | 27 | 13.3 ms | 4.2 ms | 15.8 ms |
| main-7-most-updated | 27 | 13.2 ms | 4.4 ms | 15.8 ms |
| narrow | 27 | 13.4 ms | 4.3 ms | 15.9 ms |
| human-centered | 4 | 3.0 ms | 1.8 ms | 3.3 ms |
| llm-as-judge | 15 | 7.3 ms | 1.7 ms | 7.7 ms |

Every Trust-Evals string's first page is within budget on the real corpus, `main-2-pop` the slowest at
74.8 ms wall p95 (an earlier run at load 12–27, before the stretch path, read 151–167 ms for it, so under
heavier load it can cross 100 ms). Its cost is not highlighting: its 88 matches cost 47 ms CPU to collect the
page and 44 ms for the facet aggregation (warm, median of 30, profiled once): warm searches over wildcard
phrases, which task-076 is about. A later page of a string with 50 or fewer matches is empty, so
those rows read only the counting.

## Rerunning
The scripts are small and not committed (they time a frozen copy against the live code): load `normalize.py`
at the base commit as a module of its own, set `openproceedings.engine.highlight.tokenize` to its `tokenize`
or the live one before each round, alternate the two round by round around `test_bench.search_endpoint` on an
index, and compare the two results with `==` first. For the tokenizer alone, alternate the two `tokenize`s
over the titles and abstracts of 3,000 records (`TantivyEngine.display`). For `report_80k`'s columns, call its
`timed`/`cpu_timed` around `search_endpoint` on an existing index.
