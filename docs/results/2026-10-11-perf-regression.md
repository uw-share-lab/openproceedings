# Schema 4's group-count regression and TASK-230's counting workers (2026-10-10 to 2026-10-11)

Written by hand from the milestone C perf report (kept outside git with the milestone's task reports), so the
figures spec 03 §Performance budgets, spec 04 §SearchResponse (`groups`, Cost) and `search._yield` cite live in the
repository. The two generated reports, `2026-10-11-bench.md` (synthetic 80k) and
`2026-10-11-bench-group-counts.md` (real corpus), stay the citable budget runs; this file holds the bisect, the
profiles and the two-search measurement that led to them.

- Machine: Apple M1 Pro, macOS-15.6.1-arm64, 8 CPUs; Python 3.12.15, tantivy 0.26.2. Load is given per
  measurement (1-minute average).
- Corpus: the synthetic 80k corpus of `tests.bench.report_80k` (`synthetic_5k.records(80000, (120, 250))`); index
  `0cc425d04aca` at commit `ab2de11b` (one index per commit was built by the bisect harness).
- Measure: `search_endpoint`'s first page (`tests/bench/test_bench.py`, as `/search` runs it, group counts at
  `ApiConfig`'s defaults), 200 rounds; milliseconds.

## Dev was already over budget on this corpus

The 2026-10-02 80k report (68.8 / 74.9 ms for main-1 / main-3-sources) predates group counts (TASK-176,
TASK-197), and `report_80k` was not regenerated after they landed. Before milestone C, dev (`9543942f`) was about
121 ms p50 for main-3-sources' first page on this corpus. Without group counts main-3-sources is 63 ms on dev and
65 ms on the milestone's tip, so what follows is all in the group counts.

## Bisect (load 3 to 5)

| commit | main-3-sources p50 / p95 | llm-as-judge p50 | counting job, serial (main-3) |
|---|---|---|---|
| dev `9543942f` | 121 / 129-141 | 17.7 | 110 |
| `f5dad7bd^` | 121 / 129 | 17.6 | n/a |
| **`f5dad7bd`** (index schema 4) | 145 / 545 | 29.3 | 133 |
| tip `93489e2f` | 145 / 538-635 | 29 | 133 |

Culprit: `f5dad7bd`. `TantivyEngine.counts` aggregated every tree's base over the whole combo, and `abstract_kind`
is a fifth nested level. Abstract presence is random per record in the synthetic corpus, so a counted base went
from 1,080 combos to 1,250-1,722 (on the real corpus `abstract_kind` follows venue and adds few). Tantivy's
`aggregate` went from 13 to 21 ms per request and the Python sum from 6 to 8.4 ms.

The p95 cliff (149 to 633 ms) came from full garbage collections: the report keeps the 80k corpus resident (about
810k tracked objects), and the extra combo tuples survived into generation 2. A probe counted 10 full collections
(380-515 ms each) in 200 rounds at the tip against 3 on dev; with a cached index and no resident corpus the same
code had no outliers (p95 166 ms).

## The fix, `566cafcd`

`counts` aggregates only the union of its trees' top-level filter fields (`status` alone when none filters); facets
still aggregate the whole combo. Membership and counts are unchanged (`test_group_counts.py`). `report_80k`, load
2.6 at the start and 2.8 at the end (commit `93489e2f-dirty`, the fix), p95:

| query | 2026-10-02 (no group counts) | before (2026-10-10) | after `566cafcd` |
|---|---|---|---|
| main-1 | 68.8 | 149.5 | 95.3 |
| main-2-pop | 61.4 | 116.5 | 96.1 |
| main-3-sources | 74.9 | 632.8 | **110.7** |
| main-4-sources | 48.8 | 125.0 | 77.7 |
| main-5-sources | 54.1 | 603.6 | 78.0 |
| main-6-sources | 51.7 | 610.8 | 64.9 |
| main-7-most-updated | 41.2 | 110.9 | 64.4 |
| narrow | 47.5 | 123.7 | 76.3 |
| human-centered | 48.3 | 66.7 | 58.1 |
| llm-as-judge | 0.8 | 30.7 | 8.4 |

main-3-sources' CPU per request went from 262 to 199 ms, with 1 full collection in 200 rounds. It was still over
budget: dev's own counting.

## TASK-230: the remainder (code `a3b67796`, cached 80k index)

- main-3-sources counts six trees (three groups). Their collections cost A 19, B 7.5, C 1.8, B∧C 9.5, A∧C 21 and
  A∧B 27 ms, run one after another on one worker: 86-93 ms. The page path takes 65 ms, so the counting job set the
  wall time (p50 108.5, p95 about 110 ms).
- The cost is Tantivy query evaluation: a plain count of each tree costs the same as its aggregation, and putting
  the filters in the query doesn't help (A∧B 29.6 ms with them, 27 ms without).
- Garbage collection no longer sets the p95: 1 full collection (~400 ms) in 200 rounds (p50 109.4, p95 111.7 ms),
  under the 5% a p95 needs, so neither the report nor the API freezes the collector.
- `_bitmap` setting one byte per document without a Python loop: 2.2 ms against 4.1 ms for 63k hits, the same
  bitmap. main-2-pop's page path went from 76.6 to 70.2 ms median, because the counting job's GIL-held bitmap work
  had been slowing it.

`ab2de11b` shares a job's trees with a helper on the other counting worker. `report_80k`
(`2026-10-11-bench.md`, load 4.4 at the start, 4.0 at the end), p95:

| query | before (`566cafcd`) | after (`ab2de11b`) |
|---|---|---|
| main-1 | 95.3 | 68.1 |
| main-2-pop | 96.1 | 74.2 |
| main-3-sources | **110.7** | **69.9** |
| main-4-sources | 77.7 | 58.1 |
| main-5-sources | 78.0 | 58.5 |
| main-6-sources | 64.9 | 51.2 |
| main-7-most-updated | 64.4 | 50.9 |
| narrow | 76.3 | 57.8 |
| human-centered | 58.1 | 59.5 |
| llm-as-judge | 8.4 | 7.4 |

CPU per request is unchanged (main-3-sources 203.5 ms): the work overlaps, it isn't removed. On the real corpus
(`2026-10-10-bench-group-counts.md`, index `9977ed00669f`, load 2.8 and 2.8) the worst first page with counts went
from 76.5 to 67.7 ms p95 (main-2-pop); main-3-sources from 37.3 to 28.0 ms and main-1 from 36.3 to 26.2 ms.

## Two searches arriving close together (TASK-230 review round 1)

On the cached 80k index with production waits (grace 50 ms, wait 2 s). Each round clears the facet memo, starts
search 1 and, after 0, 20 or 50 ms, search 2, each on its own thread. 100 rounds per pair and delay. Before is the
single-worker code (`a3b67796`); after is `a8c27478`. Run alternately, twice each, at a 1-minute load of 2.8 to
5.8.

**`busy` (and every other `not_counted`): 0 of 1,800 searches in each run, before and after.**

Second search, p50 / p95 (run 1 → run 2):

| pair, delay | before (single worker) | after (shared) |
|---|---|---|
| main-3 then main-2-pop, +0 | 132/148 → 125/139 | 130/164 → 118/134 |
| main-3 then main-2-pop, +20 | 116/130 → 113/128 | 114/171 → 105/120 |
| main-3 then main-2-pop, +50 | 100/115 → 99/118 | 84/100 → 81/95 |
| main-2-pop then main-3, +0 | 133/153 → 133/151 | 126/158 → 126/142 |
| main-2-pop then main-3, +20 | 136/156 → 135/146 | 82/96 → 83/99 |
| main-2-pop then main-3, +50 | 127/169 → 124/137 | 69/83 → 69/82 |
| main-1 then main-4, +0 | 89/102 → 88/106 | 92/108 → 91/107 |
| main-1 then main-4, +20 | 99/112 → 96/112 | 88/103 → 83/99 |
| main-1 then main-4, +50 | 97/106 → 96/100 | 60/72 → 61/72 |

Arriving together, the shared code matches the single worker. With 20-50 ms between them the second search is
usually faster. The worst cells (run 1, main-3 then main-2-pop at +0 and +20) started at a load of 5.4 and are
level with before in run 2: read as noise, not a regression.

## Memory

Measured with `tracemalloc` (Python 3.12.15, on the machine above): each figure is the traced allocation after
building the objects, divided by their number. Allocation sizes don't depend on load; the load is given as the
report's rule asks.

| What | Method | Figure | When, load |
|---|---|---|---|
| A memoised five-field facet combo with its count (`faceted`, schema 4) | 300 bases of 1,000 random `(venue, year, track, status, abstract_kind)` tuples with an int count each, stored as sorted tuples in a dict, as `combos` keeps them (years 1980–2026, so most are ints above 256 and separate objects) | **about 204 bytes** a combo: a full `faceted` (300,000) about 61 MB per engine, about 18 MB at schema 3's 100,000; with the default `pinned_indexes` of 4, about 300 MB of `faceted` per API process at worst, against about 90 MB at schema 3 | 2026-10-10, load 42.7 (gate C round 1); repeated 2026-10-11, load 3.3, same figure |
| A held id in `RemovalMemo` (`records.py`) | 100,000 `secrets.token_urlsafe(9)` ids, then a dict of each to a `Removal` (slots; track and status strings shared) | **about 163 bytes** an id (61 for the id string, 102 for the dict slot and the `Removal`): about 80 MB per API process when the memo is full at the default `max_ids` of 500,000 | 2026-10-11, load 25 to 26 (gate C round 2); repeated 2026-10-11, load 3.3, same figure |
| An entry in `RemovalMemo` that removed nothing | 20,000 entries offered to a memo with `removals` returning `{}` (a key tuple, an empty dict, a five-key tally); 10,000 held under the entry cap | **about 500 bytes** a held entry (about 550 on the repeat): the default entry cap of 10,000 keeps them to about 5 MB | 2026-10-11, load 25 to 26 (gate C round 2), and the repeat at load 3.3 |

## Caveats

- The bisect, profile, two-search and memory scripts were scratch harnesses and are not in the repository; the two
  generated reports above are the reproducible runs, and §Memory gives each memory figure's method.
- `2026-10-10-bench-group-counts.md` records commit `ab2de11b-dirty`: dirty only because the regenerated 80k
  report was not yet committed, not because the code differed. The file keeps its 2026-10-10 name although the
  generator dated its heading 2026-10-11 (the UTC date rolled over during the run); citations use the file name.
