---
id: TASK-057
title: 'Nightly workflow: differential@50k, full benchmarks, parity'
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-10-02 08:58'
labels:
  - ops
milestone: m-4
dependencies:
  - TASK-028
  - TASK-031
  - TASK-054
ordinal: 56000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 08 CI table, nightly row. As built: differential@50k as 8 seeded matrix jobs (stems at the 200-expansion cap's edge added to the differential corpus), a benchmarks job (5k budgets asserted, then the synthetic ~80k report into the run summary and an artifact), the property jobs under pytest-xdist, and long pytest steps that fail with ::error:: and name the unfinished test instead of timing out silently. Parity is the synthetic run in suite-ci (decision-004).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 nightly workflow runs on schedule and reports failures
- [x] #2 Pinned actions, contents: read
- [x] #3 Wildcard strategies include stems near the 200-expansion cap on the 5k fixture (carried from task-017)
- [x] #4 Differential@50k (backend/tests/differential, ~1 h locally at 50k) runs in its own nightly job; the properties job ignores it until then (task-028)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Nightly (TASK-057): new differential job (8 matrix shards x 6,250 examples at the nightly profile, OP_DIFFERENTIAL_SHARDS=8, per-shard --hypothesis-seed printed with a rerun command; suite-ci and properties ignore backend/tests/differential); new benchmarks job (5k benchmarks with spec 03 budgets asserted, then report_80k into the run summary and a bench-80k artifact); properties and properties-oracle now under pytest-xdist (serially they were cancelled at 120/150 min every night 2026-09-28..10-01); long pytest steps run -v inside timeout --signal=INT so an overrun fails with ::error:: and the log shows the unfinished test. Parity: synthetic-corpus parity (test_parity.py) runs in suite-ci; real-corpus parity stays local (decision-004). AC2 was already met (every action pinned by SHA, permissions contents: read; unchanged, upload-artifact pinned like e2e.yml). AC3: the 5k corpus has no stem between 117 and 278 terms, so cap_records() adds 20 records giving qca* 199, qcb* 200, qcc* 201 (refused) terms; cap_vocab() draws them one stem in ten; test_the_cap_stems_sit_at_the_cap pins it in both engines.

Review round 1 fixes: job renamed benchmarks (bench is bench.yml's PR check); report_80k lists budgeted numbers past their budget (Over budget section; ::warning:: in GitHub Actions; position-verified strings exempt when cold); the report step has a 45-min step limit and runs/uploads unless cancelled or the sync failed; cap words include one-letter-longer forms so $ on a cap stem expands too; CAP_STEMS ordered with the exact cap first; cap_records hash-pinned (CAP_HASH). AC #4's ~1 h estimate: measured ~0.15 CPU-s per example locally, ~2 h CPU at 50k, hence 8 shards.

Proof run 36972065571 (15bd468): suite-ci 14 min; differential 8 shards 10-20 min each, all green; benchmarks 20 min (5k 30 s, 80k report 19.5 min, nothing over budget); properties-oracle 133 min green (one 100-min test); properties overran 130 min (test_clauses year-edit property unfinished) and showed a real falsifying example in test_normalize tail (text U+0CE2, blob AEEAg+Czog==, reported to the team lead, not fixed here); mutate cancelled at 45 min after 63 of 548 mutants (full run ~6.5 h on 4 CPUs, over the 6 h cap: sharding mutate.py is a deferral). Fix: properties is a 5-part matrix split by measured time per test; long steps set OP_EARLY_FAILURES=1 so a failure's report and blob print when it fails.
<!-- SECTION:NOTES:END -->
