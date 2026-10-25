# When normalizing in worker processes pays: `PARALLEL_FROM` (TASK-284)

Regenerate from `backend/`, on a quiet machine (load under 5):

    uv run python -m tests.bench.normalize_crossover --words 120,250
    uv run python -m tests.bench.normalize_crossover --words 8,60

The tables below measured `normalized()` as of commit `bb94dc1d` (the record-count decision, unchanged since in
what it normalizes). The first two passes ran the same loop from a scratch script, before
`backend/tests/bench/normalize_crossover.py` was committed. The third ran the committed script on the branch's
working tree, which adds only the `parallel` argument and its log fields.

`engine/index.py`'s `normalized()` (shared by `build_index` and `check_parity`) normalizes titles and abstracts
either in the calling process or in a spawn `ProcessPoolExecutor` of `os.cpu_count()` workers. Until
TASK-284 it started the pool once a 4,096-record chunk held 2,000 records. Every test build of the 5k fixture
did that, and the measurements below show that a pool costs more than it saves there. The decision now reads
the snapshot manifest's `record_count` before the first chunk, and starts a pool from 10,000 records.

## Method

`normalized()` was iterated to the end over synthetic corpora of the fixture generator
(`tests/fixtures/corpus/synthetic_5k.records(n, words)`), with `workers=1` (serial) and `workers=8` (a pool:
`PARALLEL_FROM` set to 1). Serial and pool runs alternated within each repeat. Each row gives the minimum wall
time, plus the median CPU time of the calling process and of its reaped workers (`resource.getrusage`
`RUSAGE_SELF` and `RUSAGE_CHILDREN`, user + sys). Run on an 8-core Apple Silicon Mac (Python 3.12.15) on
2026-10-24 and 2026-10-25.

The machine was never quiet, so each pass states its load (the 1-minute average, from other sessions' test suites
and a mutation run):

| pass | abstracts | repeats | load |
|---|---|---:|---|
| 1, "quieter" | both lengths | 3 | 3.8-10.5 |
| 2, loaded | 120-250 words | 6 | 50-272 |
| 3, loaded, committed script | both lengths | 5 | 186-224 |

The quieter pass is above the load of 5 a timing should run under. An 8-worker pool is the run competing load slows
most, so its wall times below are, if anything, too high. CPU time is the figure other load moves least.

## Results (pass 1, load 3.8-10.5)

Abstracts of 120-250 words (realistic: `report_80k.py`'s corpus, about 1,320 characters of title and abstract
per record):

| records | serial wall | pool wall | serial CPU | pool CPU (self + children) |
|---:|---:|---:|---:|---:|
| 1,000 | 0.31 s | 0.43 s | 0.31 s | 0.08 + 2.10 s |
| 2,000 | 0.62 s | 0.52 s | 0.62 s | 0.15 + 2.44 s |
| 5,000 | 1.59 s | 0.81 s | 1.60 s | 0.34 + 3.52 s |
| 10,000 | 3.23 s | 1.25 s | 3.20 s | 0.75 + 5.16 s |
| 20,000 | 6.59 s | 2.64 s | 6.94 s | 1.52 + 8.56 s |

Abstracts of 8-60 words (the 5k fixture's, about 276 characters per record):

| records | serial wall | pool wall | serial CPU | pool CPU (self + children) |
|---:|---:|---:|---:|---:|
| 1,000 | 0.06 s | 0.34 s | 0.06 s | 0.06 + 1.74 s |
| 2,000 | 0.12 s | 0.35 s | 0.12 s | 0.09 + 1.79 s |
| 5,000 | 0.33 s | 0.45 s | 0.33 s | 0.18 + 1.99 s |
| 10,000 | 0.65 s | 0.65 s | 0.65 s | 0.38 + 2.19 s |
| 20,000 | 1.50 s | 1.17 s | 1.57 s | 0.88 + 2.70 s |

## The loaded passes, against pass 1

Pass 2, 120-250 words, minimum walls (serial / pool):

| records | pass 2 | pass 1 |
|---:|---|---|
| 1,000 | 0.34 / 0.40 s | 0.31 / 0.43 s |
| 5,000 | 1.75 / 0.80 s | 1.59 / 0.81 s |
| 10,000 | 3.43 / 1.75 s | 3.23 / 1.25 s |
| 40,000 | 13.59 / 5.11 s | not run |

At the threshold row (10,000) the pool's wall time is 40% higher loaded than in pass 1, so the wall-time
crossover is only as good as pass 1's load allows.

Pass 3's wall times (load 186-224) are dominated by waiting for a CPU. They are kept only for their CPU columns:
- 8-60 words: serial 0.07, 0.15, 0.36, 0.74 and 1.51 s at 1,000-20,000 records, within 0.09 s of pass 1. The pool's
  workers took 3.34-4.48 s against pass 1's 1.74-2.70 s: start-up costs more CPU under contention.
- 120-250 words: serial 0.36, 0.74, 1.77 and 3.59 s at 1,000-10,000 records, against pass 1's 0.31-3.20 s.

## Reading

- Starting the pool costs about 1.7 s of CPU in pass 1 (8 interpreters, each importing `openproceedings` and
  `tantivy`: the workers' CPU at 1,000 short records), more under load, and about 0.3 s of wall time, whatever the
  corpus. The pool's total CPU never falls below the serial CPU: a pool trades CPU for wall time.
- Where a pool's wall time drops below serial depends on text length, not record count. Realistic abstracts break
  even at about 1,500 records, the fixture's short ones at about 10,000. Both are roughly 2-3 million characters of
  title and abstract. On a quiet machine the short-text crossover may be somewhat lower.
- Below 10,000 records the most a pool saves is about 2 s (realistic text, 3.23 s against 1.25 s at 10,000), and
  it always costs its 1.7 s or more of CPU. Inside the test suite that CPU is multiplied by the xdist workers,
  which is the load TASK-284 traced.
- The ~80k corpus stays well past the threshold. Task-023's local bench of 80k synthetic records from the real
  corpus's text took 129.9 s before parallel normalizing and 32.9 s with it. `report_80k.py`'s latest report gives
  13.8 s for its 80,000 records (`docs/results/2026-10-11-bench.md`).

## Decision

`PARALLEL_FROM = 10_000`, compared with the manifest's `record_count` before any chunk is read, so `CHUNK` (4,096)
no longer needs to be at least `PARALLEL_FROM`. Every build of the 5k fixture is now serial wherever it runs:
the tests, the e2e fixture server and the deploy smoke test's `fixture_data.py` (all three build through
`tests/contract/conftest.build`). A full corpus still uses the pool.

Both paths give the same documents in the same order (guarantee 4). `test_index.py` checks it with the parallel
rows, which set `PARALLEL_FROM` themselves: at every served tokenizer, and on the synthetic 5k fixture.

`index_build_started` and `index_parity_ok` log `workers` and `parallel`. A readable manifest whose `record_count`
is missing or not a whole number is not refused: `iter_records` never reads that field. Such a snapshot normalizes
on one process, gives the same index, and logs one `snapshot_record_count_unreadable` WARNING.

A threshold by characters would track the crossover more closely, but a record count is known before anything is
read, and a misjudged corpus near the threshold loses at most about 2 s.
