# A process pool decided from the first chunk made every test build start eight interpreters

**Key lesson:** Decide whether to start a process pool from the whole job's size, known before any work (a manifest's record count), at a crossover you measured in CPU as well as wall time, and keep test builds serial: a pool only buys wall time and always costs its start-up CPU (~1.7 s for 8 spawn workers here), so a threshold the test fixture crosses multiplies that by every build in every xdist worker.

- **Date:** 2026-10-24 · **Task:** task-284 · **Area:** engine
- **Artifacts:** `backend/src/openproceedings/engine/index.py` (`normalized`, `PARALLEL_FROM`), `backend/src/openproceedings/engine/parity.py`, `backend/tests/conftest.py` (`_serial_index_builds`), `backend/tests/unit/engine/test_index.py`, `pyproject.toml` (`faulthandler_timeout`), `.github/workflows/nightly.yml`, `docs/results/2026-10-24-parallel-normalize-crossover.md`, commits 18c4437f, bb94dc1d

## What we set out to do
Find why the full `make test` stalled for 35-66 minutes at 93-98% (twice on 2026-10-23, load average 110 on 8
cores, one xdist worker starting a fresh spawn `ProcessPoolExecutor` about every second) and stop it.

## What we learned
- **The fixture was over the threshold, so every test build used the pool.** `normalized()` started a pool of
  `os.cpu_count()` spawn workers once a 4,096-record chunk held `PARALLEL_FROM` = 2,000 records. The synthetic 5k
  corpus does, so each of about 63 builds per suite run started 8 interpreters (each importing `openproceedings`
  and `tantivy`) inside an xdist worker: about 500 extra interpreters a run, beside the slow Hypothesis properties
  (evidence: commit 18c4437f; `testing-standards` §Index builds in tests).
- **A pool never saves CPU.** Measured on 8 cores: start-up costs about 1.7 s of CPU and 0.3 s of wall time
  whatever the corpus; at 5,000 of the fixture's short records the pool took 0.45 s wall against 0.33 s serial,
  and 2.17 s CPU against 0.33 s (evidence: `docs/results/2026-10-24-parallel-normalize-crossover.md`, both
  tables). Under xdist, where every core is already busy, the wall-time win disappears and only the CPU cost is left.
- **The crossover depends on characters, not records.** Realistic 120-250-word abstracts break even near 1,500
  records, the fixture's 8-60 words near 10,000; both are about 2-3 million characters (same note). The decision
  uses the record count anyway, because it is known before anything is read; a misjudged corpus near the line
  loses at most about 2 s.
- **Deciding from the first chunk was the wrong input.** The manifest's `record_count` now decides before the first
  chunk, at 10,000, so `CHUNK` no longer has to be at least `PARALLEL_FROM`
  (`test_index.py::test_the_record_count_not_the_first_chunk_decides_on_a_pool`).
- **A generator that owns a pool must be closed by its caller.** `_add_all` and `check_parity` now wrap
  `normalized()` in `contextlib.closing`, so a refusal shuts the pool down at once instead of when the traceback is
  collected (`test_a_build_that_fails_part_way_has_shut_its_pool_when_the_error_arrives`).
- **A stall with no trace costs a day.** `faulthandler_timeout = 1200` dumps every thread's stack once for a test
  still running at 20 minutes; the 50,000-example nightly steps, whose tests legitimately run that long, pass
  `-o faulthandler_timeout=0`.

## Dead ends — don't repeat these
- Suspecting the branch the stall was seen on (it touched `logs.py` and two openreview_v1 regexes, neither on the
  index path) or a slow regex (a native sample showed `_sre` and tantivy rayon frames): the tell was the worker
  starting a fresh spawn pool every second, so look first at what starts processes (task-284's description).
- Reading timings under a 1-minute load of 50-272: use minimum wall and CPU time, which held within ~10% of a
  quieter pass (crossover note §Method).

## Decisions (and what would change them)
- `PARALLEL_FROM = 10_000` by record count → the fixture stays serial everywhere it is built (tests, the e2e
  fixture server, the deploy smoke test's `fixture_data.py`), the ~80k corpus keeps the pool → a threshold by
  characters if a real corpus near 10,000 records shows the ~2 s loss matters.
- The test session sets `PARALLEL_FROM` to `sys.maxsize` → a larger test corpus can't reintroduce the pools; the
  parallel path keeps its own equality rows (guarantee 4) that set the threshold themselves.

## Follow-ups
- None.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/testing-standards/SKILL.md` (index builds in tests run in
  one process; the 20-minute stack dump) and `.claude/skills/tantivy-indexing/SKILL.md` (when the pool starts, its
  cost and crossover, callers close the generator), both on this branch.
- Test or hook added? — `backend/tests/conftest.py` `_serial_index_builds`; `test_index.py` fails if a default
  build of 10,000 records starts a pool, and on a pool left running after a failed build.
