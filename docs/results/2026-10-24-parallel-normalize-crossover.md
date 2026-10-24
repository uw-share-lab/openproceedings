# When normalizing in worker processes pays: `PARALLEL_FROM` (TASK-284)

`engine/index.py`'s `normalized()` (shared by `build_index` and `check_parity`) normalizes titles and abstracts
either in the calling process or in a spawn `ProcessPoolExecutor` of `os.cpu_count()` workers. Until
TASK-284 it started the pool once a 4,096-record chunk held 2,000 records. Every test build of the 5k fixture
did that, and the measurements below show that a pool costs more than it saves there. The decision now reads
the snapshot manifest's `record_count` before the first chunk, and starts a pool from 10,000 records.

## Method

`normalized()` was iterated to the end over synthetic corpora of the fixture generator
(`tests/fixtures/corpus/synthetic_5k.records(n, words)`), with `workers=1` (serial) and `workers=8` (a pool:
`PARALLEL_FROM` set to 1). Serial and pool runs alternated within each repeat. The table gives the minimum wall
time, plus the median CPU time of the calling process and of its reaped children (`resource.getrusage`
`RUSAGE_SELF` and `RUSAGE_CHILDREN`, user + sys). Run on an 8-core Apple Silicon Mac (Python 3.12.15) on
2026-10-24. The scratch script was not committed: its loop is the paragraph above.

Two passes were run:
- A loaded pass: 6 repeats per row at 120-250-word abstracts. The 1-minute load average was 50-272, from other
  sessions' test suites and a mutation run.
- A quieter pass: 3 repeats per row at both abstract lengths. The load average was 3.8-10.5.

Under load, CPU time and minimum wall time are the figures that hold up. The loaded pass agreed with the quieter
one within about 10%.

## Results (quieter pass; load 3.8-10.5)

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

The loaded pass, at 120-250 words, gave minimum walls of 0.34 / 0.40 s at 1,000 records (serial / pool), 1.75 /
0.80 s at 5,000, 3.43 / 1.75 s at 10,000 and 13.59 / 5.11 s at 40,000.

## Reading

- Starting the pool costs about 1.7 s of CPU (8 interpreters, each importing `openproceedings` and `tantivy`)
  and about 0.3 s of wall time, whatever the corpus. The pool's total CPU never falls below the serial CPU: a
  pool trades CPU for wall time.
- Where a pool's wall time drops below serial depends on text length, not record count. Realistic abstracts break
  even at about 1,500 records, the fixture's short ones at about 10,000. Both are roughly 2-3 million characters of
  title and abstract.
- Below 10,000 records the most a pool saves is about 2 s (realistic text at 5,000-10,000 records), and it always
  costs its ~2 s of CPU. Inside the test suite that CPU is multiplied by the xdist workers, which is the load
  TASK-284 traced.
- The ~80k corpus (`report_80k.py`; 129.9 s before parallel normalizing, 38.8 s with it) stays well past the
  threshold.

## Decision

`PARALLEL_FROM = 10_000`, compared with the manifest's `record_count` before any chunk is read, so `CHUNK` (4,096)
no longer needs to be at least `PARALLEL_FROM`. Every build of the 5k fixture is now serial wherever it runs:
the tests, the e2e fixture server and the deploy smoke test's `fixture_data.py` (all three build through
`tests/contract/conftest.build`). A full corpus still uses the pool. Both paths give the same documents in the
same order (guarantee 4: `test_index.py`'s parallel rows, which set `PARALLEL_FROM` themselves). A manifest with
an unreadable count is read as 0, so it builds serially; `iter_records` refuses such a snapshot anyway. A threshold
by characters would track the crossover more closely, but a record count is known before anything is read, and
a misjudged corpus near the threshold loses at most about 2 s.
