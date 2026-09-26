---
id: TASK-028
title: 'Differential suite: TantivyEngine == ReferenceEngine'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
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
- [ ] #1 0 counterexamples in 2,000 examples per CI run on the fixture snapshot
- [ ] #2 Counterexamples are minimised and saved as golden cases
- [ ] #3 Runs in the test workflow; 50k nightly job planned in M4
<!-- AC:END -->
