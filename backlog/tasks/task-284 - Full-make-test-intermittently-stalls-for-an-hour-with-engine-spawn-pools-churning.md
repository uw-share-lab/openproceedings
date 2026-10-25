---
id: TASK-284
title: >-
  Full make test intermittently stalls for an hour with engine spawn pools
  churning
status: In Progress
assignee:
  - '@jeevanparmar'
created_date: '2026-10-23 17:57'
updated_date: '2026-10-25 15:16'
labels:
  - test
  - engine
dependencies: []
priority: medium
ordinal: 186000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Seen twice on 2026-10-23 in TASK-275's branch (4f47fe8f, 92295b74), both times passing on a plain rerun (5-8 min): pytest stuck at 93-98% for 35-66 min, 4 xdist workers at ~85% CPU, one worker starting a fresh 4-process spawn ProcessPoolExecutor about every second (engine/index.py normalized(): a pool once a corpus reaches PARALLEL_FROM = 2,000 records), load average 110 on 8 cores. A native sample of the busy worker showed _sre fullmatch/match and tantivy rayon frames, not scrub's sub. The slowest tests in passing runs are the Hypothesis properties in tests/unit/test_group_counts.py (117-148 s) and tests/differential. Not caused by the branch (it changes logs.py and two author-splitting regexes in ingest/sources/openreview_v1.py, TASK-276; neither is on the engine/index path); suspect a generated corpus over PARALLEL_FROM, or pools left running by a normalized() generator that is never exhausted or closed (its finally only runs at collection).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Identify which test spawns the pools and why (faulthandler_timeout dump of a stalled run, or a reproduction with a fixed Hypothesis seed)
- [x] #2 The full suite no longer stalls: pools are closed deterministically and/or tests stay under PARALLEL_FROM, with a test that fails on a leaked pool
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-24: identified by a census plugin (no stall dump existed): 63 pools/run, all shut down, none inside Hypothesis examples; each from a 5k test build at 8 spawn workers (~500 interpreters/run inside xdist workers). Fix: the test session builds serially (conftest), callers close normalized() (closing()); regression test fails on dev. Follow-ups done in-branch: PARALLEL_FROM=10,000 decided from the manifest's record count (crossover note docs/results/2026-10-24-parallel-normalize-crossover.md); faulthandler_timeout=1200 (off in the 50k nightly steps). Full make test: 9630 passed in 6:08, no stall.

2026-10-25 (review round 1): pooled(snapshot, workers) decides the pool once per build or parity check; index_build_started and index_parity_ok log workers and parallel; a readable manifest with no whole-number record_count builds serially and logs one snapshot_record_count_unreadable WARNING (error: the value's type, or missing). Pool tests per served tokenizer (2, 3) and on the 5k fixture; the measurement loop committed as backend/tests/bench/normalize_crossover.py; a test pins PARALLEL_FROM at 10,000.
<!-- SECTION:NOTES:END -->
