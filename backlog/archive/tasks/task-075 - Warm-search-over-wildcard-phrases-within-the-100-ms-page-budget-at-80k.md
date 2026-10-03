---
id: TASK-075
title: Warm search over wildcard phrases within the 100 ms page budget at 80k
status: To Do
assignee: []
created_date: '2026-09-26 22:22'
updated_date: '2026-09-26 22:46'
labels:
  - engine
  - performance
milestone: m-4
dependencies:
  - TASK-031
ordinal: 74000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
task-031's 80k report (docs/results/2026-09-26-bench.md): main-2-pop (wildcard phrases such as model$, position-verified) searches in 147 ms p95 even with every verified clause cached, over spec 03's 100 ms budget for a 50-hit search; every other Trust-Evals string is within budget. The cached id sets still feed a term_set_query next to the full candidate query, whose scoring over ~4.4k matches dominates. Options: cache the compiled Tantivy query per (canonical, index_version), or score verified candidates from the cached ids only.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 main-2-pop warm search p95 < 100 ms in report_80k.py on a quiet machine
- [ ] #2 Differential suite green; scores unchanged (determinism test)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Not reproduced: the 147 ms came from a 20-round run, where the p95 is the slowest round, with other load on the machine. After task-031's review (40 rounds, quiet machine, report regenerated at c9fee21), main-2-pop's warm search is 63 ms p95, within the 100 ms budget. Archived; reopen if a quiet-machine report shows a warm search over budget.
<!-- SECTION:NOTES:END -->
