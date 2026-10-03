# Warm searches over wildcard phrases: the shorter id list (2026-10-02, TASK-076)

Spec 03 §Performance budgets: a 50-hit search, p95 under 100 ms. task-031 found `main-2-pop` (wildcard phrases
such as `"large language model$"`, every clause position-verified and cached) searching warm at p95 95 ms and
p99 148 ms in a 200-run probe on the synthetic 80k corpus (task-031's probe, not in docs/results); TASK-076 asks for p95 under 50 ms and p99 under
100 ms over 200 warm rounds in `report_80k`, on a quiet machine, with no change to any id set or score.

- Machine: macOS-15.6.1-arm64, 8 CPUs; Python 3.12.9, tantivy 0.26.2. Code: the alternating runs timed
  `01e8632`, the branch before its rebase onto dev; its engine and bench code are the branch's `8f47903` (a
  formatting-only reflow apart), and the rebase brought TASK-088's tokenizer, no engine change. `report_80k`
  was rerun at `66a50d3` (the review's test and comment fixes; its `-dirty` is the report file itself).
- Indexes: the synthetic 80k corpus (`report_80k` builds its own in a scratch directory; the alternating runs
  used a scratch build of the same corpus, index `27659e65468c`), and the real M4 corpus, index
  `05a0541717f6` (95,877 records), opened read-only in the main checkout's `data/indexes/`.
- No `pytest` or mutation process ran on the machine during any run below; the 1-minute load average was
  3.7–4.0 for the alternating runs and 5.7–5.9 for `report_80k` (5-minute average 9–10.5). Other agents were active but idle.

## Where a warm search went
Profiled warm (the compiled query and every verified clause cached): nearly all of a `main-2-pop` search is
Tantivy's own collection (0.78 s of 0.90 s over 30 searches, cProfile), and timing its parts showed why. A
verified clause compiles to its candidate query (every item present in the field) AND a constant-0 term set
on `id` of the ids that held the position check, and Tantivy resolves an id term set afresh on every search,
about 0.5–1.3 µs an id: on the synthetic corpus the abstract clause `"AI agent$"` holds 20,752 ids (10.7 ms of a
24.5 ms search), and on the real corpus `"large language model$"` holds 11,378 of its 13,935 candidates
(15.1 ms). Compiling once per tree (task-076's first option) was already done at the M2 gate; the remaining cost
is per search.

## What changed
`Compiler.exact`: when fewer of a verified clause's candidates failed the check than passed it, the clause is
its candidate query with the failures excluded (`MUST_NOT` a term set of their ids); when none failed, the
candidate query alone. The candidates are a superset of the verified ids, so either form matches exactly the
verified ids; the exclusion adds no score, as the constant-0 term set added 0.0, so each match scores as its
candidate query alone, the same float. Choosing costs one count of the candidate query per verified clause when the tree compiles (memoised per
tree), plus one collection of it when the count says the failures are fewer. The compiled memo charges
each clause's ids once for the Python list and once for whichever list the Tantivy query holds.

On the real corpus this cuts `main-2-pop`'s id sets from 21,762 ids to 7,547. On the synthetic corpus the big
clause has more failures (53,620) than passes, so it keeps its ids and nothing changes there.

## Proof that no id set or score changed
- `tests/unit/engine/test_verified_exclusion.py`: on a crafted corpus, each form is chosen when it should be
  (the failures, the ids, or no id set), alone and inside AND, OR and NOT trees, and matches the reference
  engine with the same float scores as the old form; on the 5k corpus, a case of each form (asserted by which
  id list the compile builds) and a nested one give the same ids and scores, and so does every tree the
  differential suite draws (`engine_asts`; drawn trees rarely reach the exclusion form, hence the cases).
  Hand mutants (the exclusion as `MUST` or `SHOULD`, excluding every candidate, never naming the failures,
  the comparison reversed) each fail it.
- `differential-regressions.json` gains a 5k tree of each new form (failures excluded; no failure), so the
  oracle replay catches a dropped or widened exclusion (the `SHOULD` mutant fails it).
- The differential suite, `test_compile.py`, `test_rank.py` (determinism, scores), `test_memo_budget.py`,
  `test_search_overlap.py` and the facet tests pass.
- Every alternating run below compared the old and new engine's whole ranked order (ids and exact float
  scores) for every Trust-Evals string before timing.

## `report_80k` (synthetic 80k, `docs/results/2026-10-02-bench.md`, new code only)

`main-2-pop`: warm search **p95 28.8 ms, p99 48.0 ms** over 200 runs (AC: under 50 ms and 100 ms). Every
non-empty string's warm p95 is 19.3–36.3 ms and p99 38.7–63.3 ms. Load 5.9 → 5.7 (1 min), but 10.5 → 9.0 over
5 minutes: the run's cold columns swing with it (`main-2-pop` 10.9 s to search, and 19.0 s for `match_ids` +
exclusions where the first run of this change, at `01e8632`, read 10.8 s; `main-3-sources`' exclusions 103 ms
against 37 ms), so read its warm p99s as upper bounds. The first run read `main-2-pop` warm p95 27.8 ms and
p99 31.7 ms (load 10.1 → 3.5; the task's notes cite it, as the CLI can't edit a completed task). The
highlight and `/search` columns of this report include TASK-088's tokenizer; `main-3-sources`' "with
highlights" p95 of 138.9 ms is a load outlier of this run (69.7 ms in the first run, and its `/search` first
page, highlights included, read 62.2 ms in the same run; this change touches no highlighting).

## Old vs new compile, 200 warm rounds each, interleaved (`backend/tests/bench/warm_verified.py`)

`search(limit=50)` on two engines over one index, one compiling as before (`members` off), alternating round
by round with the order flipping. A wall p99 well above its CPU p99 is the machine preempting the process, not
the search.

Real M4 corpus (load 3.8 → 4.0):

| String | Matches | Wall p50: old | new | Wall p95: old | new | Wall p99: old | new | CPU p50: old | new | CPU p99: old | new |
|---|---|---|---|---|---|---|---|---|---|---|---|
| main-1 | 50 | 5.4 ms | 5.4 ms | 5.7 ms | 5.6 ms | 15.8 ms | 8.5 ms | 5.3 ms | 5.3 ms | 6.2 ms | 6.4 ms |
| main-2-pop | 88 | 44.9 ms | 26.2 ms | 46.8 ms | 27.3 ms | 71.4 ms | 58.8 ms | 44.7 ms | 26.0 ms | 49.2 ms | 31.2 ms |
| main-3-sources | 50 | 5.7 ms | 5.7 ms | 6.0 ms | 6.0 ms | 10.0 ms | 10.4 ms | 5.7 ms | 5.7 ms | 6.2 ms | 6.9 ms |
| main-4-sources | 27 | 3.7 ms | 3.7 ms | 3.9 ms | 3.9 ms | 4.0 ms | 4.0 ms | 3.7 ms | 3.7 ms | 4.0 ms | 3.9 ms |
| main-5-sources | 21 | 3.6 ms | 3.6 ms | 3.9 ms | 4.1 ms | 7.7 ms | 6.2 ms | 3.5 ms | 3.6 ms | 4.0 ms | 4.3 ms |
| main-6-sources | 27 | 3.6 ms | 3.6 ms | 3.8 ms | 3.9 ms | 23.0 ms | 6.8 ms | 3.6 ms | 3.6 ms | 4.7 ms | 4.3 ms |
| main-7-most-updated | 27 | 3.5 ms | 3.6 ms | 3.8 ms | 3.7 ms | 3.9 ms | 3.8 ms | 3.5 ms | 3.5 ms | 3.8 ms | 3.8 ms |
| narrow | 27 | 3.4 ms | 3.4 ms | 3.6 ms | 3.6 ms | 6.6 ms | 8.0 ms | 3.4 ms | 3.4 ms | 3.8 ms | 4.6 ms |
| human-centered | 4 | 1.0 ms | 1.0 ms | 1.2 ms | 1.2 ms | 1.4 ms | 1.4 ms | 1.0 ms | 1.0 ms | 1.2 ms | 1.3 ms |
| llm-as-judge | 15 | 1.1 ms | 1.1 ms | 1.3 ms | 1.3 ms | 1.5 ms | 1.4 ms | 1.1 ms | 1.1 ms | 1.4 ms | 1.4 ms |

Synthetic 80k corpus (load 3.9 → 3.7):

| String | Matches | Wall p50: old | new | Wall p95: old | new | Wall p99: old | new | CPU p50: old | new | CPU p99: old | new |
|---|---|---|---|---|---|---|---|---|---|---|---|
| main-1 | 4,298 | 33.6 ms | 33.6 ms | 34.4 ms | 34.6 ms | 55.1 ms | 57.4 ms | 33.4 ms | 33.4 ms | 36.6 ms | 36.2 ms |
| main-2-pop | 4,417 | 27.0 ms | 26.9 ms | 28.1 ms | 28.0 ms | 53.3 ms | 51.2 ms | 26.8 ms | 26.8 ms | 29.6 ms | 30.5 ms |
| main-3-sources | 4,298 | 34.0 ms | 34.0 ms | 35.0 ms | 34.9 ms | 55.7 ms | 56.8 ms | 33.8 ms | 33.8 ms | 35.3 ms | 36.2 ms |
| main-4-sources | 3,980 | 23.9 ms | 23.9 ms | 24.6 ms | 25.0 ms | 36.9 ms | 47.8 ms | 23.8 ms | 23.8 ms | 26.3 ms | 26.1 ms |
| main-5-sources | 3,907 | 23.2 ms | 23.2 ms | 23.9 ms | 23.7 ms | 43.6 ms | 50.2 ms | 23.1 ms | 23.1 ms | 24.6 ms | 25.5 ms |
| main-6-sources | 4,062 | 17.4 ms | 17.4 ms | 18.0 ms | 17.9 ms | 20.1 ms | 18.8 ms | 17.3 ms | 17.3 ms | 18.5 ms | 18.5 ms |
| main-7-most-updated | 4,062 | 17.5 ms | 17.4 ms | 18.1 ms | 18.1 ms | 20.2 ms | 40.0 ms | 17.4 ms | 17.4 ms | 19.1 ms | 18.8 ms |
| narrow | 3,980 | 23.6 ms | 23.6 ms | 24.4 ms | 24.7 ms | 45.7 ms | 44.3 ms | 23.5 ms | 23.5 ms | 25.0 ms | 25.7 ms |
| human-centered | 278 | 24.2 ms | 24.2 ms | 25.0 ms | 25.1 ms | 46.6 ms | 25.6 ms | 24.0 ms | 24.1 ms | 25.3 ms | 25.1 ms |
| llm-as-judge | 0 | 0.6 ms | 0.6 ms | 0.8 ms | 0.7 ms | 0.9 ms | 0.9 ms | 0.6 ms | 0.6 ms | 0.9 ms | 0.8 ms |

On the real corpus `main-2-pop`'s warm search costs 42% less (p50 44.9 → 26.2 ms, p95 46.8 → 27.3 ms, CPU p99
49.2 → 31.2 ms); every other string, and the synthetic corpus, is unchanged within noise, as expected (no
clause of theirs has fewer failures than passes, or none is verified). The synthetic `main-2-pop` already met
the AC on a quiet machine before this change (old p95 28.1 ms): task-031's 95/148 ms came from a loaded
machine. An earlier alternating run at load 27 read `main-2-pop`'s real-corpus wall p99 at 160 ms old and
140 ms new while its CPU stayed near 36 ms: preemption, not the search.

## What stays
The synthetic `"AI agent$"` clause, 20,752 ids against 53,620 failures, still costs ~10 ms a search to resolve;
neither list is short. A form that resolves no id list per search (an id set Tantivy could keep between
searches, or a per-document fast-field filter) needs a Tantivy API tantivy-py 0.26 doesn't expose, or a schema
change; not needed for the budget today.

## Rerunning
`uv run python -m tests.bench.warm_verified INDEX` (from `backend/`) for the alternating tables, and
`uv run python -m tests.bench.report_80k` for the report.
