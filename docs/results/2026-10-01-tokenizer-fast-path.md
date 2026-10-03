# The tokenizer loop's fast paths, and `/search` on the real corpus (2026-10-01, TASK-088)

Spec 03 §Performance budgets: the first 50 hits, p95 under 100 ms. After the M3a review gate every Trust-Evals
string's `/search` first page was under budget in wall time on the synthetic 80k corpus, but its CPU per
request (what bounds throughput) was unchanged at 74–109 ms, and a third of it on `main-1` was highlighting,
almost all of that `query/normalize.py`'s per-character loop (task-088). This records the loop's new fast
paths, the proof that no token changed, and `/search` re-measured on the real M4 corpus, with the method, so
it can be rerun.

- Machine: macOS-15.6.1-arm64, 8 CPUs; Python 3.12.9, tantivy 0.26.2. Old code: `query/normalize.py` at
  `05eff53`; new code: `952401a`, the timed commit (`2275836` after the branch's rebase onto dev, with an identical
  `backend/`; later commits change docs only).
- Indexes: the real M4 corpus, index `05a0541717f6` (95,877 records), opened read-only in the main checkout's
  `data/indexes/`; the synthetic 80k corpus (`tests/fixtures/corpus/synthetic_5k.records(80_000, (120, 250))`),
  built in a scratch directory, never under `data/`.
- **Nearly quiet.** Other agents were active but idle: no `pytest` or mutation process ran anywhere on the
  machine at the start or end of any table, and the 1-minute load average was 3.9–7.7 (from outside
  openproceedings: Spotlight indexing, a browser). Old and new code alternate round by round in one process,
  the order flipping each round, so what load there was weighs on both alike.
- Harness: `backend/tests/bench/alternate.py` (`search`, `tokenize` and `columns`; its docstring has the
  commands). Every table below is its output.

## What changed
All in `_tokenize_each_char`, the loop every text takes unless it is ASCII with no `\` or `$` (task-073's
whole-text path). Each is the same steps the loop took one character at a time, done in fewer Python steps:
- A text with no `\` and no `$` skips `_latex_mask`: math and commands need one of the two, so the mask would
  be all KEEP.
- A stretch of ASCII characters that are all KEEP, with no combining mark after its last, is taken word by
  word with `[A-Za-z0-9]+`: each word appends to the open word or, when a separator follows it in the
  stretch, is a token at once; each run of separators closes the open word and joins the `Tail`. Where a
  stretch ends is one regular-expression search, in the text for the next non-ASCII character (kept until
  the loop passes it, so the searches stay linear) and, for a text with markup, in the mask as bytes.
  `close()` skips NFC and the marks-only test for an ASCII word.
- `_fold_char(c, base)` folds a raw character once per process when its fold doesn't depend on `base`.
  `_fold` reads `base` only through `_folds_marks`, which tells apart five classes of base (none, or a
  letter whose marks all fold; Cyrillic, which keeps the breve; Arabic, which keeps hamza; any other script,
  which keeps every mark), and returns it when no piece replaces it, so a character whose `_fold` is the
  same after one base of each class, `None` and `"a"` both (`_BASES`), is the same after any base. The table
  (`_FOLDED`) is bounded at 4,096 characters; once it is full, a character not in it is folded once, as
  before.

`TOKENIZER_VERSION` stays `2`; no index is rebuilt.

Why these: a profile of `tokenize` over 3,000 real records' titles and abstracts, before the change (cProfile,
1.97 s in all), put 0.75 s in the loop's own steps and 0.58 s in `close()`; `_fold` was not in the top 12.
Of the real texts that leave the whole-text path (18%), two thirds do so for a `$` or `\` and the rest for a
non-ASCII character (most often `’`, `—`, `–`, curly quotes, `×`, accented letters), so the cost was the
ASCII between the few odd characters, not the odd characters.

## Proof that no token changed
- `tests/unit/tokenize_before_088.py` is a frozen copy of the loop at `05eff53` (TASK-067's linear runs of
  marks included). `test_highlight_speed.py` holds the loop and `tokenize_with_tail` to it, tokens (text,
  span, `op`) and `Tail`, on arbitrary, ASCII, LaTeX-heavy, combining-mark and Latin-with-typography text
  (a new strategy) and on every text of the fixture and 5k corpora; task-073's oracle,
  `tests/unit/tokenize_before.py`, still holds `tokenize` too.
- `test_a_cached_fold_is_the_fold_after_any_base` checks `_fold_char` against `_fold` for any character
  after any base (Hypothesis). Once, by hand: every code point (surrogates excluded) whose fold is the same
  after `_BASES` (1,110,698 of them) and has a mark in its decomposition gave the same fold after a base of
  each of 5,759 Unicode name prefixes (no exception). `OP_EXHAUSTIVE=1 tests/unit/test_normalize_exhaustive.py`
  (every code point in 8 contexts against the whole-string definition) passed.
- The review gate added: 300k random inputs against the frozen loop, tokens and `Tail` (0 differences); every
  code point's fold after 16 bases of different scripts (0 differences); and `parse` of 20,032 queries with
  the old and new loop (0 differences in the whole `ParseResult`).
- Hand mutants of the new code: dropping the `Tail` reset, the span's markup start, the `k -= 1` before a
  mark, the NFC, the stretch's base reset, the reuse of the next non-ASCII position (linear-time tests), or
  caching a base-dependent fold each fail a test. Equivalent survivors: the marks-only test skipped for ASCII
  words, an ASCII letter as the base after a stretch (it is in the same class as no base), and dropping the
  Cyrillic or Arabic base (`None` and Thai alone catch any mark that reads the base).
- Every `/search` timed below compared the old and new tokenizer's whole `Search` result (hits, scores,
  highlights, facets, exclusions) with `==` before timing, and the tokenizer table compared every text's
  tokens.

## The tokenizer alone: 3,000 records' titles and abstracts, 30 rounds, interleaved, CPU time (median)

| Corpus | Texts | Count | Old | New | Ratio |
|---|---|---|---|---|---|
| real M4 | every text | 6,000 | 979.8 ms | 723.0 ms | 74% |
| real M4 | texts off the whole-text ASCII path | 1,083 | 593.6 ms | 333.7 ms | 56% |
| synthetic 80k | every text | 6,000 | 1,776.6 ms | 1,049.5 ms | 59% |
| synthetic 80k | texts off the whole-text ASCII path | 3,132 | 1,736.3 ms | 1,050.0 ms | 60% |

Load 7.7 → 5.8 (real), 3.9 → 3.9 (synthetic).

## `/search` first page: old vs new tokenizer, 200 rounds each, interleaved

`test_bench.search_endpoint` (`search.run(limit=50, facets=True, highlight=True)`, the facet memo cleared
each round, as a query's first page pays). Wall time is what a client waits; CPU (process time, every thread)
is what bounds throughput.

Real M4 corpus (load 7.4 at the start, 7.7 at the end):

| String | Matches | Wall p50: old | new | Wall p95: old | new | CPU p50: old | new | CPU p95: old | new |
|---|---|---|---|---|---|---|---|---|---|
| main-1 | 50 | 30.6 ms | 22.5 ms | 32.3 ms | 26.1 ms | 35.5 ms | 27.4 ms | 36.8 ms | 29.2 ms |
| main-2-pop | 88 | 69.9 ms | 63.1 ms | 83.6 ms | 70.5 ms | 115.8 ms | 108.7 ms | 125.5 ms | 119.4 ms |
| main-3-sources | 50 | 31.0 ms | 22.9 ms | 32.2 ms | 23.8 ms | 36.0 ms | 27.9 ms | 36.9 ms | 28.8 ms |
| main-4-sources | 27 | 17.4 ms | 12.9 ms | 18.0 ms | 13.4 ms | 20.6 ms | 16.1 ms | 21.1 ms | 16.6 ms |
| main-5-sources | 21 | 13.7 ms | 10.9 ms | 14.1 ms | 11.3 ms | 16.6 ms | 13.9 ms | 17.1 ms | 14.3 ms |
| main-6-sources | 27 | 16.1 ms | 12.7 ms | 16.9 ms | 13.1 ms | 19.0 ms | 15.6 ms | 19.8 ms | 16.1 ms |
| main-7-most-updated | 27 | 16.0 ms | 12.6 ms | 16.6 ms | 13.0 ms | 19.0 ms | 15.6 ms | 19.5 ms | 16.0 ms |
| narrow | 27 | 17.0 ms | 12.6 ms | 17.6 ms | 13.1 ms | 20.1 ms | 15.8 ms | 20.8 ms | 16.3 ms |
| human-centered | 4 | 3.2 ms | 2.7 ms | 3.6 ms | 3.0 ms | 3.9 ms | 3.3 ms | 4.3 ms | 3.7 ms |
| llm-as-judge | 15 | 9.4 ms | 6.7 ms | 9.7 ms | 7.1 ms | 10.3 ms | 7.7 ms | 10.6 ms | 8.0 ms |

Synthetic 80k corpus (load 5.7 at the start, 4.0 at the end):

| String | Wall p50: old | new | Wall p95: old | new | CPU p50: old | new | CPU p95: old | new |
|---|---|---|---|---|---|---|---|---|
| main-1 | 71.1 ms | 58.9 ms | 91.8 ms | 60.8 ms | 104.4 ms | 92.2 ms | 107.2 ms | 94.4 ms |
| main-2-pop | 70.8 ms | 58.2 ms | 86.7 ms | 63.9 ms | 100.8 ms | 88.1 ms | 108.7 ms | 96.9 ms |
| main-3-sources | 71.7 ms | 59.6 ms | 85.1 ms | 64.4 ms | 105.0 ms | 93.0 ms | 108.0 ms | 95.7 ms |
| main-4-sources | 59.5 ms | 48.0 ms | 63.2 ms | 53.9 ms | 83.4 ms | 71.9 ms | 85.9 ms | 75.6 ms |
| main-5-sources | 59.6 ms | 47.9 ms | 68.9 ms | 51.8 ms | 83.0 ms | 71.3 ms | 86.6 ms | 73.7 ms |
| main-6-sources | 54.2 ms | 42.1 ms | 57.1 ms | 44.8 ms | 71.8 ms | 59.7 ms | 74.0 ms | 61.6 ms |
| main-7-most-updated | 54.2 ms | 42.1 ms | 55.5 ms | 45.1 ms | 71.7 ms | 59.7 ms | 73.2 ms | 61.3 ms |
| narrow | 59.1 ms | 47.6 ms | 60.2 ms | 48.7 ms | 83.0 ms | 71.5 ms | 84.2 ms | 72.7 ms |
| human-centered | 60.4 ms | 48.2 ms | 62.0 ms | 49.3 ms | 84.2 ms | 71.9 ms | 85.6 ms | 73.2 ms |
| llm-as-judge | 0.8 ms | 0.8 ms | 0.9 ms | 1.0 ms | 1.3 ms | 1.3 ms | 1.4 ms | 1.4 ms |

The median first page costs 11.5–12.7 ms less CPU on the synthetic corpus for every non-empty string, and
0.6–8.1 ms less on the real one (fewer matches there, and fewer of their texts leave the whole-text path).
New wall p95: 3.0–70.5 ms on the real corpus, 44.8–64.4 ms on the synthetic one (every non-empty string).

## `report_80k`'s `/search` columns on the real M4 corpus (new code only)

`report_80k`'s own functions (`timed`, `cpu_timed`, `p95`, `ENDPOINT_ROUNDS` = 200) over the real index:
first page with the facet memo cleared, a later page (offset 50) with it warm, both wall p95, and the first
page's mean CPU per request. Load 5.8 at the start, 5.7 at the end.

| String | Matches | `/search`, first page: p95 wall | a later page: p95 wall | first page: CPU per request |
|---|---|---|---|---|
| main-1 | 50 | 23.1 ms | 6.3 ms | 27.3 ms |
| main-2-pop | 88 | 73.4 ms | 64.6 ms | 112.5 ms |
| main-3-sources | 50 | 45.9 ms | 6.5 ms | 28.2 ms |
| main-4-sources | 27 | 13.5 ms | 4.4 ms | 16.2 ms |
| main-5-sources | 21 | 11.5 ms | 4.2 ms | 13.7 ms |
| main-6-sources | 27 | 12.9 ms | 4.2 ms | 15.6 ms |
| main-7-most-updated | 27 | 12.8 ms | 4.4 ms | 15.5 ms |
| narrow | 27 | 13.3 ms | 4.0 ms | 15.8 ms |
| human-centered | 4 | 2.9 ms | 1.4 ms | 3.2 ms |
| llm-as-judge | 15 | 7.1 ms | 1.7 ms | 7.5 ms |

Every Trust-Evals string's first page is within budget on the real corpus. `main-2-pop` is the slowest at
73.4 ms wall p95 and 112.5 ms CPU, with most of its time outside highlighting: profiled warm (median of 30),
collecting its page cost 47 ms CPU and its facet aggregation 44 ms, for 88 matches. Warm searches over
wildcard phrases are task-076. `main-3-sources`' 45.9 ms is a wall-time outlier of this run (its CPU per
request is 28.2 ms, as `main-1`'s, and the interleaved run read 23.8 ms). A later page of a string with 50 or
fewer matches is empty, so those rows read only the counting. An earlier run of the first version of this
change (before the review gate) at load 12–27 read 151–167 ms for `main-2-pop`: under heavy load its wall
p95 can cross 100 ms, as any CPU-bound request can.
