---
id: TASK-284
title: >-
  Full make test intermittently stalls for an hour with engine spawn pools
  churning
status: To Do
assignee: []
created_date: '2026-10-23 17:57'
labels:
  - test
  - engine
dependencies: []
priority: medium
ordinal: 186000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Seen twice on 2026-10-23 in TASK-275's branch (4f47fe8f, 92295b74), both times passing on a plain rerun (5-8 min): pytest stuck at 93-98% for 35-66 min, 4 xdist workers at ~85% CPU, one worker starting a fresh 4-process spawn ProcessPoolExecutor about every second (engine/index.py normalized(): a pool once a corpus reaches PARALLEL_FROM = 2,000 records), load average 110 on 8 cores. A native sample of the busy worker showed _sre fullmatch/match and tantivy rayon frames, not scrub's sub. The slowest tests in passing runs are the Hypothesis properties in tests/unit/test_group_counts.py (117-148 s) and tests/differential. Not caused by the branch (it changes only logs.py and a comment in openreview_v1.py); suspect a generated corpus over PARALLEL_FROM, or pools left running by a normalized() generator that is never exhausted or closed (its finally only runs at collection).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Identify which test spawns the pools and why (faulthandler_timeout dump of a stalled run, or a reproduction with a fixed Hypothesis seed)
- [ ] #2 The full suite no longer stalls: pools are closed deterministically and/or tests stay under PARALLEL_FROM, with a test that fails on a leaked pool
<!-- AC:END -->
