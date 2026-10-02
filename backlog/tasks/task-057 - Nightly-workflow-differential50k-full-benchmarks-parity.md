---
id: TASK-057
title: 'Nightly workflow: differential@50k, full benchmarks, parity'
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-10-02 05:20'
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
Spec 08 CI table (planned workflows).
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
Nightly (TASK-057): new differential job (8 matrix shards x 6,250 examples at the nightly profile, OP_DIFFERENTIAL_SHARDS=8, per-shard --hypothesis-seed printed with a rerun command; suite-ci and properties ignore backend/tests/differential); new bench job (5k benchmarks with spec 03 budgets asserted, then report_80k into the run summary and a bench-80k artifact); properties and properties-oracle now under pytest-xdist (serially they were cancelled at 120/150 min every night 2026-09-28..10-01); long pytest steps run -v inside timeout --signal=INT so an overrun fails with ::error:: and the log shows the unfinished test. Parity: synthetic-corpus parity (test_parity.py) runs in suite-ci; real-corpus parity stays local (decision-004). AC2 was already met (every action pinned by SHA, permissions contents: read; unchanged, upload-artifact pinned like e2e.yml). AC3: the 5k corpus has no stem between 117 and 278 terms, so cap_records() adds 20 records giving qca* 199, qcb* 200, qcc* 201 (refused) terms; cap_vocab() draws them one stem in ten; test_the_cap_stems_sit_at_the_cap pins it in both engines.
<!-- SECTION:NOTES:END -->
