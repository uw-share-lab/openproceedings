---
id: TASK-028
title: 'Differential suite: TantivyEngine == ReferenceEngine'
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 21:13'
labels:
  - engine
milestone: m-2
dependencies:
  - TASK-024
  - TASK-017
  - TASK-006
ordinal: 27000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 07 §A (differential-tester, reference-oracle skills).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 0 counterexamples in 2,000 examples per CI run on the fixture snapshot
- [x] #2 Counterexamples are minimised and saved as golden cases
- [x] #3 Runs in the test workflow; 50k nightly job planned in M4
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented: tests/fixtures/corpus/synthetic_5k.py (5,000 records generated in memory, deterministic; vocabulary and n-grams shared with tests/strategies.py so random trees hit documents; LaTeX, NFKC forms, marks, CJK, astral, invisible separators; every venue × year × track × status; some missing abstracts) and tests/differential/test_differential.py over engine_asts() (parser-valid, bare and all-negative trees): match sets, expand results or refusals, disjunctive facets (oracle only for fields with their own top-level conjunct; the rest counted from the known match set, which cut 85 s to 15 s at 200 examples), and total for every sort. CI profile: 0 counterexamples in 2,000 examples, 2.5 min. Regressions file seeded with 11 hard shapes, replayed every run. Teeth: 5 engine mutants (NEAR slop, one NEAR order, phrase slop, $ as *, empty expansion as all) all fail it. filters() now draws every track/status of the vocabulary (it missed tiny_papers, blogpost, competition, other, desk_rejected). Nightly: the properties job ignores the differential until task-057's own 50k job (it would take ~1 h locally, over that job's limit); task-057 gained that AC.
<!-- SECTION:NOTES:END -->
