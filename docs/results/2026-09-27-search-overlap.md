# `/search` facets overlapped with the page, and a faster BibTeX writer (2026-09-27, M3a review gate round 2)

Spec 03 §Performance budgets: the first 50 hits, p95 under 100 ms. After task-086 a `/search` first page
(`search.run(limit=50, facets=True, highlight=True)`) at 80k was 75–117 ms p95 in CPU time, over budget for
`main-1` and `main-3-sources` (task-088). This records the change that brings every Trust-Evals string under
100 ms wall p95, with the method, so it can be rerun.

- Machine: macOS-15.6.1-arm64, 8 CPUs; Python 3.12.9, tantivy 0.26.2; code: `30756ce` plus this change.
- Index: the synthetic 80k corpus (`tests/fixtures/corpus/synthetic_5k.records(80_000, (120, 250))`, 80,000
  documents, built in a scratch directory, never under `data/`).
- **Not a quiet machine.** Other agents' test suites ran throughout: the 1-minute load average was 14.2 at
  the start of the `/search` run and 5.7 at its end (it reached 58 during the day's other runs). The
  before/after numbers alternate the two versions round by round in one process, so load weighs on both
  alike; read the differences with more confidence than the absolute times.

## What changed
- `search.run` compiles the effective tree first (a cold position-verified clause is verified there, in the
  request's thread, holding at most one verification slot), then starts `TantivyEngine.facets` on a worker
  thread (`search._pool()`, a module-level `ThreadPoolExecutor`, the caller's `contextvars` copied, shut down
  at exit and forgotten after a fork) and collects the page, reads its display records and highlights it
  meanwhile. Tantivy releases the GIL while it collects, so the facet collection and the page collection
  overlap. Then `fut.result()` and exclusion accounting (which reads the facet memo the worker filled).
- `export._braced` skips each pass whose character doesn't occur (no brace: no balance count; no `&%#`: no
  escaping; no `@`: no `{@}`), and escapes `&%#` with one pass over `(\\*)([&%#])` that adds a backslash
  after an even run only, instead of a look-behind pattern run over every value.

## Proof that no output changed
- `/search`: `tests/unit/test_search_overlap.py` holds `search.run` to a frozen copy of the sequential run,
  on two engines over one 5k index (each with its own memos): every Trust-Evals string, first and second page,
  facets and highlights on; and 150 Hypothesis queries (`tests.strategies.queries`: phrases with `model$`,
  NEAR, NOT, filters) under all four sorts, refusals compared by type, code and message. The 80k run below
  asserted `==` for every string's first and second page before timing it. A worker's error is re-raised as
  the same object; the caller's error wins when both fail; bad arguments are refused before the worker starts.
- A cold verified `/search` with `verification_slots=1` is served, verifying in the request's thread only
  (`tests/contract/test_search_overlap.py`; with the up-front compile removed, all three cases are refused
  503 `API_BUSY` against themselves).
- BibTeX: every export format (BibTeX, RIS, CSV, JSONL) of every document of the 5k corpus, of
  `test_export.py`'s fixture corpus and of the 80k corpus hashed the same before and after (12 sha256s, all
  equal), and the timing run below compared the two outputs of each round byte for byte.
  `tests/unit/test_export_braced.py` holds `_braced` and `_balances` to frozen copies of the old functions
  under Hypothesis (backslash-dense text and arbitrary text).

## `/search` at 80k: sequential vs overlapped, 200 rounds each, interleaved

First page: the facet memo cleared each round (as a query's first page pays); later page: offset 50, the
memo warm. Wall p95 is what a client waits; CPU per request (mean, process time, every thread) is what
bounds throughput, and the overlap doesn't change it.

| String | First page, wall p95: sequential | overlapped | Later page, wall p95: sequential | overlapped | First page, CPU per request: sequential | overlapped |
|---|---|---|---|---|---|---|
| main-1 | 116.0 ms | **84.5 ms** | 82.9 ms | 76.6 ms | 108.2 ms | 108.7 ms |
| main-2-pop | 95.1 ms | **79.3 ms** | 74.5 ms | 66.9 ms | 91.6 ms | 104.9 ms |
| main-3-sources | 110.5 ms | **76.8 ms** | 77.2 ms | 75.3 ms | 108.2 ms | 108.3 ms |
| main-4-sources | 88.6 ms | **63.7 ms** | 64.3 ms | 62.5 ms | 85.9 ms | 85.9 ms |
| main-5-sources | 87.3 ms | **63.4 ms** | 62.2 ms | 61.0 ms | 85.6 ms | 85.2 ms |
| main-6-sources | 83.1 ms | **63.2 ms** | 61.3 ms | 56.4 ms | 74.8 ms | 75.1 ms |
| main-7-most-updated | 75.9 ms | **57.3 ms** | 55.6 ms | 54.0 ms | 73.6 ms | 73.8 ms |
| narrow | 87.4 ms | **62.7 ms** | 63.8 ms | 62.6 ms | 85.4 ms | 85.7 ms |
| human-centered | 92.0 ms | **66.5 ms** | 63.5 ms | 61.9 ms | 87.8 ms | 87.6 ms |
| llm-as-judge | 1.3 ms | 0.9 ms | 0.9 ms | 0.9 ms | 1.2 ms | 1.3 ms |

Every non-empty Trust-Evals string's first page is under 100 ms wall p95 (the largest, `main-1`, 84.5 ms;
wall saved on a first page 18–34 ms, about the facet collection). CPU per request is unchanged within noise;
`main-2-pop`'s overlapped CPU reading (+13 ms) was its first timed row and is not seen in any other string.
The bench row (`test_search_endpoint_first_page`, 5k fixture, now 100 rounds, wall time) read medians of
0.5–13.6 ms, maximum 28.9 ms, at load 50–58.

## BibTeX export: frozen vs guarded `_braced`, 5 rounds each, interleaved, CPU time

| Export | Records | Frozen (median) | Guarded (median) | Ratio |
|---|---|---|---|---|
| `main-1`'s matches | 4,298 | 732 ms | 224 ms | 31% |
| every document | 80,000 | 15,791 ms | 6,917 ms | 44% |

Load average 5.7 at the start, 15.3 at the end. The output of every round was identical.

## Rerunning
The scripts are small and not committed (they time a frozen copy against the live code): for `/search`,
alternate `search.run` and `tests.unit.test_search_overlap.sequential` on an 80k index round by round,
clearing `engine.faceted` before each first page; for BibTeX, alternate `export._braced` with
`tests.unit.test_export_braced._old_braced` around `export.write("bibtex", …)`. `report_80k` now reports
`/search` as wall p95 over 200 rounds plus CPU per request.
