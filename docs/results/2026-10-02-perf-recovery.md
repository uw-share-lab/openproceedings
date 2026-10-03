# TASK-166/167 recovery measurements

The historical `2026-10-02-exclusions-and-verified-forms.md` measurements ran at load 30–155 on 8 CPUs.
They show no measurable end-to-end schema gain. The isolated 11.3 → 6.2 ms claim is historical and lacked
a committed in-index harness separating Python construction from Tantivy collection.

The recovery uses read-only, same-snapshot schema-2/schema-3 indexes and the shared `heavy.sh` lock.
Both schema-comparison harnesses verify manifests and require identical snapshot_hash, tokenizer_version,
ranking_params and tantivy_version before loading/timing; matching document IDs alone is insufficient.
`tests.bench.id_sets OLD_INDEX NEW_INDEX 100` measures the abstract AI-agent wildcard clause's text-id
and ordinal query construction separately from collection of preconstructed queries. It reports ordinal
table first/subsequent construction, whole-tree compile with verified/expansion caches warm but compiled
cache cleared (table first use versus retained), compile memo hits, and retained table memory from the
dict plus integer values, excluding existing id strings. This is an object-size estimate, not RSS.

`tests.bench.exclusions_alternate 5k 200` compares all-facet COMBO aggregation and track/status ORDER
aggregation, alternated each round, asserting equal exclusion counts before timing. Warm runs keep the
facet memo; cold aggregation runs clear only that memo. Load is printed before each phase.
`test_bench` preserves the original all-facet broad benchmark and adds the narrower caller separately.

`tests.bench.schemas_alternate OLD_INDEX NEW_INDEX 200` checks every Trust-Evals string's whole ID and
float-score order in every sort, facets and exclusions before timing whole warm searches alternately.

`tests.bench.report_80k ../docs/results/2026-10-02-schema-3-bench.md` builds its own synthetic 80k index.
Cold runs clear every engine cache: compiled queries, verified clauses, wildcard expansions, facet combos
and the lazy ordinal lookup. The opened index and OS page cache remain warm. Exclusion-only reporting
uses `over=ORDER`; older reports retained some caches and aggregated COMBO, so cold columns are not
comparable. The fresh measurements below were generated on code `ace8a1de` before the reversible Backlog history
reconstruction; raw output is retained and the production/benchmark source is unchanged by reconstruction.


## Fresh paired measurements

macOS 15.6.1 arm64, 8 CPUs, Python 3.12.9, Tantivy 0.26.2. Indexes `27659e65468c` (schema 2) and
`83f44f4eb82f` (schema 3), both snapshot
`2391ef1c4f6a56640772e8a080b8980f1251246d7cb9ebf114b8cc80b72cd3fc`, tokenizer 2, and identical
ranking inputs. Each harness verifies these manifest inputs before timing. Shared heavy lock held.

Paired phase starts: id_sets load 3.5 / 74.7% CPU idle; exclusions5k load 3.2 / 70.6% idle;
schemas80k load 3.2 / 80.8% idle. No active swap-in/out was observed in the phase-start samples.
Pre-existing swap usage was about 13.2 GB; this machine was CPU quiet, with memory already under pressure.

### Construction, collection and lookup memory (100 rounds)

Construction times are CPU time for the Python call into the Tantivy query factory, including its binding
work and disposal of temporary queries; they are separate from the timed collections of preconstructed
queries. Whole-tree compile rows retain verified clauses/expansions, isolating lookup first-use versus
retained lookup; they do not represent first position verification on a fresh engine.

| Phase | CPU p50 | CPU p95 |
|---|---|---|
| text construction | 3.7 ms | 4.1 ms |
| ordinal first construction | 8.2 ms | 9.6 ms |
| ordinal subsequent construction | 4.7 ms | 5.6 ms |
| text collection | 9.7 ms | 10.3 ms |
| ordinal collection | 5.6 ms | 5.9 ms |
| tree compile, table first use | 25.4 ms | 28.2 ms |
| tree compile, table retained | 21.8 ms | 24.7 ms |
| tree compile memo hit | 0.1 ms | 0.1 ms |

Retained ordinal table: **4,162,480 bytes**, estimated from dict plus integer values, excluding existing id
strings; this is not RSS. First-use lookup adds about 3.5 ms to query construction and3.6 ms to compilation.
Ordinal construction is slightly slower than text-ID construction here, while collection is faster.
The historical 11.3→6.2 ms figure is not treated as a reproducible phase-separated result.

### Exclusions, all facets versus defaults (200 alternating rounds)

Counts were exactly equal before timing for every protocol string and the broad query. The original broad
COMBO benchmark remains separately named in test_bench; ORDER is an added benchmark. The broad warm
CPU/wall median 1.5→0.6 ms is below the old about 1.46 ms target for the exclusion-only caller; COMBO remains
about 1.5 ms. Cold here clears only the facet memo, not verification/compilation/ordinal lookup.

| String | Combos: facets | defaults | Warm p50: facets | defaults | Warm p95: facets | defaults | Warm CPU p50: facets | defaults | Cold p50: facets | defaults | Cold p95: facets | defaults |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| main-1 | 629 | 45 | 1.7 ms | 1.1 ms | 2.0 ms | 1.3 ms | 1.7 ms | 1.1 ms | 3.1 ms | 1.7 ms | 3.4 ms | 1.9 ms |
| main-2-pop | 656 | 45 | 2.5 ms | 1.9 ms | 2.8 ms | 2.1 ms | 2.5 ms | 1.9 ms | 4.8 ms | 3.3 ms | 5.3 ms | 3.6 ms |
| main-3-sources | 629 | 45 | 1.8 ms | 1.2 ms | 2.0 ms | 1.4 ms | 1.8 ms | 1.2 ms | 3.2 ms | 2.0 ms | 3.6 ms | 2.3 ms |
| main-4-sources | 452 | 45 | 1.3 ms | 0.9 ms | 1.4 ms | 1.1 ms | 1.3 ms | 0.9 ms | 2.4 ms | 1.5 ms | 2.6 ms | 1.7 ms |
| main-5-sources | 379 | 45 | 1.2 ms | 0.9 ms | 1.3 ms | 1.0 ms | 1.2 ms | 0.9 ms | 2.2 ms | 1.4 ms | 2.5 ms | 1.6 ms |
| main-6-sources | 473 | 45 | 1.2 ms | 0.8 ms | 1.3 ms | 0.9 ms | 1.2 ms | 0.8 ms | 2.4 ms | 1.3 ms | 2.6 ms | 1.6 ms |
| main-7-most-updated | 473 | 45 | 1.2 ms | 0.8 ms | 1.3 ms | 0.9 ms | 1.2 ms | 0.8 ms | 2.3 ms | 1.3 ms | 2.6 ms | 1.5 ms |
| narrow | 452 | 45 | 1.1 ms | 0.8 ms | 1.3 ms | 0.9 ms | 1.1 ms | 0.8 ms | 2.3 ms | 1.2 ms | 2.6 ms | 1.4 ms |
| human-centered | 36 | 27 | 0.7 ms | 0.7 ms | 0.8 ms | 0.8 ms | 0.7 ms | 0.7 ms | 1.2 ms | 1.0 ms | 1.3 ms | 1.2 ms |
| llm-as-judge | 0 | 0 | 0.4 ms | 0.4 ms | 0.5 ms | 0.5 ms | 0.4 ms | 0.4 ms | 0.5 ms | 0.5 ms | 0.6 ms | 0.6 ms |
| broad (test_bench) | 1080 | 45 | 1.5 ms | 0.6 ms | 1.7 ms | 0.7 ms | 1.5 ms | 0.6 ms | 3.0 ms | 0.8 ms | 3.3 ms | 1.0 ms |

Load at each printed warm/cold boundary ranged 3.1–3.3 (start 3.2/end 3.2).

### Complete warm searches on both schemas (200 alternating rounds)

Every whole ID/float-score order in every sort, every facet and every exclusion count was exactly equal
before timing for all 10 strings. No end-to-end speedup is demonstrated. The wildcard-heavy main-2-pop median
is slightly slower on schema 3 (CPU 25.2→26.0 ms), while its wall p95 is essentially equal 27.6→27.5 ms.

| String | Matches | Wall p50: schema 2 | 3 | Wall p95: 2 | 3 | Wall p99: 2 | 3 | CPU p50: 2 | 3 | CPU p99: 2 | 3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| main-1 | 4,298 | 32.5 ms | 32.5 ms | 33.7 ms | 34.0 ms | 34.8 ms | 34.9 ms | 32.4 ms | 32.5 ms | 34.5 ms | 34.2 ms |
| main-2-pop | 4,417 | 25.2 ms | 26.1 ms | 27.6 ms | 27.5 ms | 30.2 ms | 34.3 ms | 25.2 ms | 26.0 ms | 28.0 ms | 28.7 ms |
| main-3-sources | 4,298 | 33.1 ms | 33.1 ms | 35.9 ms | 35.3 ms | 41.4 ms | 42.5 ms | 33.0 ms | 33.1 ms | 37.2 ms | 36.4 ms |
| main-4-sources | 3,980 | 23.7 ms | 23.6 ms | 38.1 ms | 29.7 ms | 49.1 ms | 107.3 ms | 23.6 ms | 23.5 ms | 29.7 ms | 28.4 ms |
| main-5-sources | 3,907 | 23.0 ms | 23.0 ms | 24.4 ms | 25.2 ms | 45.9 ms | 57.6 ms | 22.9 ms | 22.9 ms | 26.9 ms | 27.5 ms |
| main-6-sources | 4,062 | 17.3 ms | 17.3 ms | 18.2 ms | 18.1 ms | 19.7 ms | 38.1 ms | 17.2 ms | 17.2 ms | 19.0 ms | 21.0 ms |
| main-7-most-updated | 4,062 | 17.3 ms | 17.3 ms | 18.1 ms | 18.1 ms | 39.0 ms | 50.6 ms | 17.2 ms | 17.3 ms | 19.5 ms | 22.9 ms |
| narrow | 3,980 | 23.4 ms | 23.4 ms | 24.2 ms | 24.7 ms | 57.5 ms | 52.4 ms | 23.3 ms | 23.3 ms | 26.4 ms | 26.4 ms |
| human-centered | 278 | 23.9 ms | 24.0 ms | 25.6 ms | 25.2 ms | 59.7 ms | 48.6 ms | 23.8 ms | 23.9 ms | 26.5 ms | 30.0 ms |
| llm-as-judge | 0 | 0.6 ms | 0.6 ms | 0.7 ms | 0.7 ms | 0.7 ms | 0.8 ms | 0.6 ms | 0.6 ms | 0.7 ms | 0.7 ms |

Load start 3.2/end 4.3. The schema choice remains the owner's exactness/replay-safe decision, with no
claimed end-to-end gain.

## Full schema-3 report

Generated artifact: [2026-10-02-schema-3-bench.md](2026-10-02-schema-3-bench.md), code `ace8a1de`.
The full default sampling schedule ran: 40 cold rounds, 200 warm rounds and200 rounds per endpoint phase.
The filename follows the task's local date; the generated header uses UTC 2026-10-03.

The controller accepted a **CPU-idle-qualified** baseline after persistent OS/IO load, rather than asserting
load<=4 throughout: two samples 20 s apart were 70.77%/71.41% idle, load 5.79/5.16, with zero active
swap-ins/outs. Shared lock excluded all other heavy jobs. Memory baseline was 15 GB used, 5.2–5.3 GB
compressed, 13.0 GB pre-existing swap. Full report load 5.1→3.2 (1-minute); after-run last sample 84.61% idle,
40 swap-in pages/0 swap-out pages. Total swap usage increased to 16.0 GB across the run, so wall timings
are observations under these recorded memory-pressure conditions, not a claim of an entirely idle machine.

Build 14.3 s, index 99 MB, largest build process peak 409 MB (workers not summed). Every budgeted number is
within budget: maximum warm-search p95 **35.5ms**, with-highlights p95 **57.8ms**, first endpoint p95
**74.9ms**, nonverified cold exclusion p95 **71.6ms**, expansion p95 **0.1ms**. main-2-pop's first cold search
**9.625s** and cold exclusion p95 **17.096s** are the position-verified exception, reported explicitly.

Cold engine memos are fully reset, including `_ords`. OS/index page caches remain warm. Older cold
reports used different retained caches/aggregation and cannot support a direct before/after claim.

## Validation

- `uv run pytest backend/tests/unit/engine/test_served_schemas.py backend/tests/unit/engine/test_facets_equal.py backend/tests/bench/test_bench.py -q --benchmark-disable`: 99 passed in 85.49 s at `bea16ca9`.
- Negative manifest-input controls: `uv run pytest backend/tests/unit/engine/test_served_schemas.py -q -k schema_bench`: 4 passed, 20 deselected in 10.84 s at `ace8a1de`.
- Full stable `f2b50e3c`, shared heavy lock, Node 22.23.3, four pytest workers: `make test` passed
  (backend **6330 passed, 2 skipped in 137.52 s**; frontend **3209 passed**, 40 files, 6.30 s);
  `make lint` and `make tooling` passed. HEAD and clean tree were unchanged throughout.
  Both tasks were finalized and completed through the Backlog CLI after these checks.


## CI comparison protocol correction

PR #91's first bench run compared the historical exclusion benchmark, which retains facet results,
with a fully cold version under the same test ID. Its 33–91% regression therefore included newly charged
facet work. Keep `test_match_ids_with_exclusion_accounting`'s historical verified/compiled/expanded-only
reset for base/head comparisons. The separately named
`test_match_ids_with_exclusion_accounting_all_engine_caches_cold` also resets faceted and `_ords` and
retains the 300 ms budget. The full report above continues to reset every engine memo. No regression
threshold or budget changes; comparable-workload CI evidence must pass before merge.
