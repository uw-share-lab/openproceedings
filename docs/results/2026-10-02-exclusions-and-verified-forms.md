# Exclusion accounting without facets, and a verified clause's id set (2026-10-02, TASK-166, TASK-167)

> Recovery correction: the historical runs below were overloaded (1-minute load 30–155 on 8 CPUs).
> They show no measurable end-to-end difference from schema 3; the apparent 0–3% change is noise,
> not a demonstrated gain. The 11.3 → 6.2 ms isolated claim did not preserve its harness and did not
> separate Python query construction from Tantivy collection. It is historical context, not fresh proof.
> The committed `tests.bench.id_sets` harness now measures those phases separately on the same index pair,
> including first-use lazy-table cost and retained memory. Fresh recovery evidence is recorded separately.
> Cold report methodology now clears all engine caches, including facet combinations and the ordinal table;
> old cold reports retained caches and cannot be compared directly.

TASK-166: a caller that needs only the exclusion counts (`op search`, a record's save or replay) paid for
every (venue, year, track, status) facet combination. TASK-167: the synthetic `"AI agent$"` clause's id set
was said to cost about 10 ms a search (`2026-10-02-wildcard-phrases.md`, What stays).

- Machine: macOS-15.6.1-arm64, 8 CPUs; Python 3.12.9, tantivy 0.26.2. Code: branch `perf/task-166-167`
  (TASK-166 at `23f8941a`, TASK-167 at `cbcb5d3e`).
- Indexes: the synthetic 80k corpus (`27659e65468c`, schema 2, a scratch build; and `83f44f4eb82f`, its
  schema-3 build), the real M4 corpus (`05a0541717f6`, 95,877 records, schema 2, opened read-only from the main
  checkout's `data/indexes/`; and `657a2fe61377`, its schema-3 build in a scratch directory), and the 5k fixture.
- **Load.** Five other agents were running on the machine throughout. The 1-minute load average was 30–155
  (each table gives its own). No `pytest` or mutation run of this branch was in flight. Every comparison
  alternates its two sides round by round, with the order flipping each round, so both sides carry the same
  load. Read the absolute numbers as upper bounds, and read the CPU columns before the wall ones.

## TASK-166: the default fields only

`TantivyEngine.facets(..., over=…)` aggregates only the named fields. Only their top-level filters are set
aside; every other field's filters stay in the collected query. `search.run` without facets passes track and
status (`exclusions.ORDER`); with facets, it still reads the combos its facet worker collected. Before timing,
the two paths' `Excluded` were compared with `==` for every string. The equality tests are
`test_facets_equal.py` (generated trees with extra top-level filters, every Trust-Evals string, and
ReferenceEngine) and `test_search_overlap.py` (a search without facets equals the sequential search).

`tests/bench/exclusions_alternate.py`: `match_ids` + `excluded`, 200 rounds a side on the 5k fixture and
100 on the 80k corpora. *Warm* is with each path's combos memoised (a later page, a repeated save). *Cold*
clears the facet memo before each call (the compiled and verified memos stay warm). `facets` is the old path,
which every search ran before this change; `defaults` is the new one.

5k fixture (load 56.5 → 68.2):

| String | Combos: facets | defaults | Warm p50: facets | defaults | Warm p95: facets | defaults | Warm CPU p50: facets | defaults | Cold p50: facets | defaults | Cold p95: facets | defaults |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| main-1 | 629 | 45 | 1.9 ms | 1.3 ms | 3.4 ms | 2.0 ms | 1.9 ms | 1.3 ms | 4.6 ms | 2.2 ms | 20.8 ms | 17.1 ms |
| main-2-pop | 656 | 45 | 2.7 ms | 2.0 ms | 8.4 ms | 6.1 ms | 2.7 ms | 2.0 ms | 7.5 ms | 4.5 ms | 44.6 ms | 41.8 ms |
| main-3-sources | 629 | 45 | 2.2 ms | 1.6 ms | 13.0 ms | 7.6 ms | 2.1 ms | 1.5 ms | 5.1 ms | 3.0 ms | 38.9 ms | 32.1 ms |
| main-4-sources | 452 | 45 | 1.5 ms | 1.1 ms | 10.7 ms | 3.9 ms | 1.5 ms | 1.0 ms | 3.0 ms | 1.8 ms | 13.9 ms | 5.2 ms |
| main-5-sources | 379 | 45 | 1.5 ms | 1.1 ms | 10.8 ms | 12.9 ms | 1.4 ms | 1.1 ms | 2.8 ms | 1.7 ms | 18.4 ms | 12.4 ms |
| main-6-sources | 473 | 45 | 1.5 ms | 1.0 ms | 5.1 ms | 2.8 ms | 1.5 ms | 1.0 ms | 2.9 ms | 1.6 ms | 4.7 ms | 2.7 ms |
| main-7-most-updated | 473 | 45 | 1.4 ms | 0.9 ms | 2.8 ms | 1.5 ms | 1.4 ms | 0.9 ms | 3.0 ms | 1.6 ms | 6.6 ms | 3.8 ms |
| narrow | 452 | 45 | 1.3 ms | 0.9 ms | 5.3 ms | 6.5 ms | 1.3 ms | 0.9 ms | 3.0 ms | 1.5 ms | 12.1 ms | 4.5 ms |
| human-centered | 36 | 27 | 0.8 ms | 0.8 ms | 3.0 ms | 2.2 ms | 0.8 ms | 0.8 ms | 1.4 ms | 1.3 ms | 13.1 ms | 8.7 ms |
| llm-as-judge | 0 | 0 | 0.5 ms | 0.5 ms | 1.6 ms | 1.8 ms | 0.5 ms | 0.5 ms | 0.6 ms | 0.6 ms | 1.1 ms | 0.9 ms |
| broad (test_bench) | 1080 | 45 | 1.7 ms | 0.7 ms | 4.5 ms | 2.2 ms | 1.7 ms | 0.7 ms | 3.7 ms | 1.0 ms | 7.0 ms | 1.9 ms |

The bench's broad query (`test_match_ids_with_exclusions_on_a_broad_query`, whose +31% PR #6 recorded) went
from a warm p50 of 1.7 ms to 0.7 ms. That is below the pre-PR #6 1.46 ms (AC #1), because the new path reads
45 combos where the old one read 1,080.

Synthetic 80k (load 68.2 → 35.7):

| String | Combos: facets | defaults | Warm p50: facets | defaults | Warm p95: facets | defaults | Warm CPU p50: facets | defaults | Cold p50: facets | defaults | Cold p95: facets | defaults |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| main-1 | 1080 | 45 | 36.5 ms | 35.2 ms | 51.8 ms | 46.7 ms | 36.2 ms | 35.0 ms | 71.5 ms | 67.8 ms | 117.3 ms | 101.9 ms |
| main-2-pop | 1080 | 45 | 34.1 ms | 33.3 ms | 87.4 ms | 68.9 ms | 30.3 ms | 29.4 ms | 61.3 ms | 56.4 ms | 140.9 ms | 108.5 ms |
| main-3-sources | 1080 | 45 | 36.6 ms | 35.5 ms | 40.6 ms | 38.6 ms | 36.4 ms | 35.3 ms | 71.5 ms | 68.8 ms | 101.6 ms | 85.9 ms |
| main-4-sources | 1080 | 45 | 25.4 ms | 24.4 ms | 26.7 ms | 26.9 ms | 25.3 ms | 24.4 ms | 49.8 ms | 47.6 ms | 53.6 ms | 49.2 ms |
| main-5-sources | 1080 | 45 | 24.7 ms | 23.6 ms | 26.2 ms | 25.0 ms | 24.7 ms | 23.5 ms | 49.0 ms | 46.7 ms | 58.6 ms | 53.6 ms |
| main-6-sources | 1080 | 45 | 18.6 ms | 17.6 ms | 20.6 ms | 19.1 ms | 18.6 ms | 17.6 ms | 38.3 ms | 35.8 ms | 83.1 ms | 48.9 ms |
| main-7-most-updated | 1080 | 45 | 18.2 ms | 17.3 ms | 19.0 ms | 18.1 ms | 18.2 ms | 17.2 ms | 37.5 ms | 35.3 ms | 41.6 ms | 40.4 ms |
| narrow | 1080 | 45 | 25.0 ms | 24.1 ms | 31.5 ms | 32.0 ms | 25.0 ms | 24.0 ms | 54.7 ms | 50.7 ms | 205.3 ms | 217.4 ms |
| human-centered | 1055 | 45 | 26.6 ms | 25.5 ms | 64.3 ms | 29.8 ms | 26.5 ms | 25.4 ms | 52.4 ms | 49.8 ms | 109.1 ms | 122.4 ms |
| llm-as-judge | 0 | 0 | 0.8 ms | 0.8 ms | 1.0 ms | 1.0 ms | 0.8 ms | 0.8 ms | 1.2 ms | 1.2 ms | 1.8 ms | 1.8 ms |

Real M4 corpus (load 36.3 → 30.6):

| String | Combos: facets | defaults | Warm p50: facets | defaults | Warm p95: facets | defaults | Warm CPU p50: facets | defaults | Cold p50: facets | defaults | Cold p95: facets | defaults |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| main-1 | 27 | 8 | 6.1 ms | 6.1 ms | 8.1 ms | 8.5 ms | 6.0 ms | 6.1 ms | 11.1 ms | 11.0 ms | 14.5 ms | 13.1 ms |
| main-2-pop | 32 | 9 | 28.8 ms | 29.1 ms | 39.8 ms | 41.2 ms | 28.4 ms | 28.4 ms | 53.4 ms | 53.0 ms | 76.8 ms | 75.4 ms |
| main-3-sources | 27 | 8 | 6.1 ms | 6.0 ms | 6.3 ms | 6.3 ms | 6.1 ms | 6.0 ms | 11.1 ms | 11.2 ms | 11.6 ms | 11.8 ms |
| main-4-sources | 22 | 8 | 4.1 ms | 4.1 ms | 4.3 ms | 4.3 ms | 4.1 ms | 4.1 ms | 7.3 ms | 7.5 ms | 9.6 ms | 8.5 ms |
| main-5-sources | 16 | 6 | 4.0 ms | 4.0 ms | 5.9 ms | 6.1 ms | 4.0 ms | 4.0 ms | 6.8 ms | 7.1 ms | 8.8 ms | 9.4 ms |
| main-6-sources | 17 | 6 | 4.0 ms | 4.0 ms | 5.8 ms | 6.3 ms | 4.0 ms | 4.0 ms | 6.9 ms | 7.2 ms | 7.9 ms | 7.8 ms |
| main-7-most-updated | 17 | 6 | 4.0 ms | 4.0 ms | 4.4 ms | 4.9 ms | 4.0 ms | 4.0 ms | 6.8 ms | 7.1 ms | 7.5 ms | 8.0 ms |
| narrow | 22 | 8 | 3.8 ms | 3.8 ms | 4.5 ms | 4.1 ms | 3.8 ms | 3.8 ms | 7.1 ms | 6.9 ms | 9.1 ms | 8.9 ms |
| human-centered | 7 | 3 | 1.4 ms | 1.3 ms | 1.8 ms | 2.0 ms | 1.3 ms | 1.3 ms | 2.0 ms | 2.0 ms | 14.1 ms | 9.7 ms |
| llm-as-judge | 12 | 5 | 1.8 ms | 1.7 ms | 7.5 ms | 8.1 ms | 1.7 ms | 1.6 ms | 2.3 ms | 2.2 ms | 4.2 ms | 3.9 ms |

On the 80k corpora `match_ids`' own collection dominates. The new path saves 1–2 ms warm on the synthetic
corpus (1,080 combos) and nothing measurable on the real one (at most 32 combos).

## TASK-167: the verified clause's id set

`tests/bench/verified_forms.py` times, for each verified clause of `main-2-pop`, one collection of: its
candidate query alone; the form the engine compiles; and a constant-0 `regex_phrase_query`. The regex phrase
is the one tantivy-py 0.26 form that resolves no id list, with each wildcard item written as an alternation of
its expansions. It also reports whether the regex phrase matched exactly the verified ids. It then times a
term set of 20,752 values over 80,000 documents, on a raw-text id and on an indexed u64. These runs are on the
schema-2 indexes, so "as compiled" is the text-`id` term set.

Synthetic 80k (load 30.6 → 98.8):

| Field | Clause | Verified | Candidates | Candidates alone | As compiled | Regex phrase | Same ids |
|---|---|---|---|---|---|---|---|
| title | `"large language model$"` | 24 | 116 | 0.1 ms | 0.2 ms | 0.3 ms | True |
| abstract | `"large language model$"` | 533 | 56,205 | 2.1 ms | 1.1 ms | 41.5 ms | True |
| title | `"vision language model$"` | 22 | 127 | 0.1 ms | 0.2 ms | 0.3 ms | True |
| abstract | `"vision language model$"` | 858 | 52,166 | 1.9 ms | 1.5 ms | 102.3 ms | True |
| title | `"ai agent$"` | 650 | 3,566 | 0.4 ms | 0.9 ms | 1.1 ms | True |
| abstract | `"ai agent$"` | 20,752 | 74,372 | 1.6 ms | 43.8 ms | 157.7 ms | True |
| title | `"trustworthy ai$"` | 100 | 594 | 0.1 ms | 0.2 ms | 0.3 ms | True |
| abstract | `"trustworthy ai$"` | 3,610 | 60,647 | 1.2 ms | 21.4 ms | 89.7 ms | True |
- term set of 20,752 on a raw-text id (as built): 95.9 ms
- term set of 20,752 on a indexed u64 ord (a schema change): 10.1 ms

Real M4 corpus (load 105.8 → 130.0):

| Field | Clause | Verified | Candidates | Candidates alone | As compiled | Regex phrase | Same ids |
|---|---|---|---|---|---|---|---|
| title | `"large language model$"` | 2,955 | 3,161 | 0.2 ms | 0.9 ms | 1.3 ms | True |
| abstract | `"large language model$"` | 11,378 | 13,935 | 1.6 ms | 16.0 ms | 29.8 ms | True |
| title | `"foundation model$"` | 874 | 897 | 0.1 ms | 0.3 ms | 0.4 ms | True |
| abstract | `"foundation model$"` | 2,100 | 3,027 | 0.4 ms | 7.0 ms | 1.7 ms | True |
| title | `"generative ai$"` | 94 | 98 | 0.1 ms | 0.2 ms | 0.2 ms | True |
| abstract | `"generative ai$"` | 369 | 916 | 0.4 ms | 1.3 ms | 0.9 ms | True |
| title | `"vision language model$"` | 637 | 788 | 0.1 ms | 0.7 ms | 0.5 ms | True |
| abstract | `"vision language model$"` | 1,550 | 3,416 | 0.6 ms | 13.2 ms | 2.7 ms | True |
| title | `"multimodal model$"` | 115 | 497 | 0.1 ms | 0.5 ms | 0.3 ms | True |
| abstract | `"multimodal model$"` | 409 | 2,647 | 0.4 ms | 1.5 ms | 1.2 ms | True |
| title | `"ai agent$"` | 80 | 118 | 0.0 ms | 0.3 ms | 0.1 ms | True |
| abstract | `"ai agent$"` | 317 | 926 | 0.1 ms | 1.1 ms | 0.5 ms | True |
| title | `"text to image model$"` | 63 | 208 | 0.1 ms | 0.4 ms | 0.3 ms | True |
| abstract | `"text to image model$"` | 198 | 2,822 | 0.8 ms | 0.9 ms | 2.0 ms | True |
| title | `"trustworthy ai$"` | 6 | 9 | 0.1 ms | 0.2 ms | 0.2 ms | True |
| abstract | `"trustworthy ai$"` | 68 | 166 | 0.3 ms | 0.6 ms | 0.5 ms | True |
| title | `"evaluation framework$"` | 31 | 64 | 0.0 ms | 0.2 ms | 0.1 ms | True |
| abstract | `"evaluation framework$"` | 477 | 2,598 | 0.3 ms | 2.1 ms | 0.9 ms | True |
| abstract | `"test suite$"` | 41 | 220 | 0.1 ms | 0.3 ms | 0.2 ms | True |
- term set of 20,752 on a raw-text id (as built): 72.4 ms
- term set of 20,752 on a indexed u64 ord (a schema change): 21.1 ms

The regex phrase matches the same ids for every clause. It costs more than the id set, though: it reads
positions for every candidate (157.7 ms against 43.8 ms for `"ai agent$"` on the synthetic corpus). A term
set on an indexed u64 resolves 3.4–9.5x faster than one on a text id in isolation. On the two 80k indexes the
`"AI agent$"` set alone measured 11.3 → 6.2 ms CPU (median of 40, `id_set` on each index).

### Schema 3 vs schema 2, the whole warm search

`tests/bench/schemas_alternate.py`: `search(limit=50)` on a schema-2 index and on a schema-3 build of the same
snapshot, 200 rounds each. Before timing, every string's whole order in every sort was compared with `==`, as
were its facets and its exclusion counts.

Synthetic 80k (load 154.8 → 122.2):

| String | Matches | Wall p50: schema 2 | 3 | Wall p95: 2 | 3 | Wall p99: 2 | 3 | CPU p50: 2 | 3 | CPU p99: 2 | 3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| main-1 | 4,298 | 185.5 ms | 172.4 ms | 392.1 ms | 403.9 ms | 730.9 ms | 502.3 ms | 38.9 ms | 38.7 ms | 44.7 ms | 45.4 ms |
| main-2-pop | 4,417 | 36.2 ms | 37.1 ms | 96.0 ms | 105.1 ms | 226.0 ms | 166.5 ms | 29.4 ms | 29.7 ms | 37.4 ms | 36.6 ms |
| main-3-sources | 4,298 | 73.4 ms | 73.3 ms | 138.1 ms | 116.5 ms | 192.6 ms | 192.3 ms | 72.1 ms | 71.8 ms | 103.8 ms | 96.9 ms |
| main-4-sources | 3,980 | 52.3 ms | 52.2 ms | 180.2 ms | 177.9 ms | 460.8 ms | 963.5 ms | 52.1 ms | 52.1 ms | 95.3 ms | 87.3 ms |
| main-5-sources | 3,907 | 27.0 ms | 28.3 ms | 300.3 ms | 300.9 ms | 846.8 ms | 772.0 ms | 25.7 ms | 25.9 ms | 80.0 ms | 78.9 ms |
| main-6-sources | 4,062 | 19.5 ms | 19.7 ms | 84.0 ms | 85.3 ms | 163.9 ms | 115.7 ms | 19.4 ms | 19.6 ms | 62.4 ms | 59.3 ms |
| main-7-most-updated | 4,062 | 18.3 ms | 18.2 ms | 62.3 ms | 62.1 ms | 114.5 ms | 104.6 ms | 18.3 ms | 18.2 ms | 62.6 ms | 60.1 ms |
| narrow | 3,980 | 27.9 ms | 28.0 ms | 96.8 ms | 100.1 ms | 184.0 ms | 181.8 ms | 26.2 ms | 26.4 ms | 79.1 ms | 77.4 ms |
| human-centered | 278 | 24.9 ms | 24.9 ms | 81.5 ms | 85.8 ms | 142.6 ms | 144.9 ms | 24.8 ms | 24.9 ms | 73.9 ms | 73.0 ms |
| llm-as-judge | 0 | 0.9 ms | 0.9 ms | 2.7 ms | 2.9 ms | 3.3 ms | 3.8 ms | 0.9 ms | 0.9 ms | 1.8 ms | 2.1 ms |

Real M4 corpus (load 122.2 → 72.6):

| String | Matches | Wall p50: schema 2 | 3 | Wall p95: 2 | 3 | Wall p99: 2 | 3 | CPU p50: 2 | 3 | CPU p99: 2 | 3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| main-1 | 50 | 5.4 ms | 5.5 ms | 19.6 ms | 25.1 ms | 105.9 ms | 71.3 ms | 5.4 ms | 5.5 ms | 19.8 ms | 19.4 ms |
| main-2-pop | 88 | 26.4 ms | 25.6 ms | 81.9 ms | 76.9 ms | 365.3 ms | 269.6 ms | 26.4 ms | 25.6 ms | 86.6 ms | 87.3 ms |
| main-3-sources | 50 | 6.1 ms | 6.1 ms | 17.0 ms | 17.4 ms | 22.2 ms | 23.1 ms | 6.1 ms | 6.1 ms | 17.8 ms | 17.9 ms |
| main-4-sources | 27 | 3.9 ms | 3.9 ms | 16.0 ms | 14.0 ms | 35.0 ms | 63.7 ms | 3.9 ms | 3.9 ms | 11.9 ms | 12.2 ms |
| main-5-sources | 21 | 3.8 ms | 3.8 ms | 5.8 ms | 5.8 ms | 31.2 ms | 13.3 ms | 3.7 ms | 3.7 ms | 6.0 ms | 6.2 ms |
| main-6-sources | 27 | 3.8 ms | 3.8 ms | 5.4 ms | 5.7 ms | 8.8 ms | 8.1 ms | 3.8 ms | 3.8 ms | 4.4 ms | 4.4 ms |
| main-7-most-updated | 27 | 5.2 ms | 5.1 ms | 15.0 ms | 11.5 ms | 34.6 ms | 18.8 ms | 5.1 ms | 5.1 ms | 13.1 ms | 12.6 ms |
| narrow | 27 | 3.6 ms | 3.6 ms | 4.0 ms | 3.9 ms | 5.7 ms | 5.4 ms | 3.5 ms | 3.5 ms | 3.9 ms | 3.9 ms |
| human-centered | 4 | 1.1 ms | 1.1 ms | 1.6 ms | 1.7 ms | 12.7 ms | 2.4 ms | 1.1 ms | 1.1 ms | 2.1 ms | 1.8 ms |
| llm-as-judge | 15 | 1.2 ms | 1.2 ms | 2.1 ms | 1.8 ms | 5.3 ms | 4.0 ms | 1.2 ms | 1.2 ms | 1.7 ms | 2.0 ms |

Inside a whole search the faster id set barely shows. `main-2-pop`'s CPU p50 is 29.4 vs 29.7 ms on the
synthetic corpus and 26.4 vs 25.6 ms on the real one. Every other string is equal within noise. The id set is
one MUST clause of an intersection that the rarer clauses drive, so most of its isolated cost (what "about
10 ms a search" measured) never lands on a search.

Schema 3 was kept by owner decision (2026-10-02) because it is exact and replay-safe, with no measurable end-to-end gain. Schema 2 stays served until no record pins a schema-2 index (spec 03 §Versioning).

### Guarantee 4 across the schema bump

- Records saved by the pre-change code (`origin/dev` at `433399a9`, a detached worktree), one for each of the
  10 Trust-Evals strings, on the real `05a0541717f6` index, in a scratch record store. This code then replayed
  them with the schema-3 `657a2fe61377` served and `05a0541717f6` pinned: **10/10 `reproduced`**.
- `tests/contract/test_records.py::test_a_record_saved_on_a_schema_2_index_reproduces_after_the_schema_3_build`
  checks the same on the 5k corpus through the API, together with identical ids, exclusions and expansions on
  both schemas.

## Rerunning
From `backend/`: `uv run python -m tests.bench.exclusions_alternate INDEX|5k`,
`uv run python -m tests.bench.verified_forms INDEX`, and `uv run python -m tests.bench.schemas_alternate OLD NEW`
(build the schema-3 index into a scratch directory with `build_index`, never into `data/indexes`).
