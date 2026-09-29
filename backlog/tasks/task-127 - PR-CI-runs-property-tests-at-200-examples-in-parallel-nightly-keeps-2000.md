---
id: TASK-127
title: 'PR CI runs property tests at 200 examples in parallel; nightly keeps 2,000'
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 22:32'
updated_date: '2026-09-29 22:32'
labels:
  - ci
  - tests
dependencies: []
ordinal: 111000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR CI's backend step takes ~25 min. Measured 2026-09-29 (--durations, ci profile): 25 Hypothesis property tests take 1,432 of 1,650 s (87%); the other 5,199 tests take 218 s. The owner chose: PR CI at the dev profile (200 examples) with pytest-xdist across the runner's CPUs; nightly runs the whole backend suite at the ci profile (2,000) in addition to its existing 50k jobs, so no property loses depth, only detection moves to within a day.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 PR CI's backend step runs the suite with pytest-xdist at the dev Hypothesis profile and finishes in well under 10 minutes on the shared runner (measured on the PR's own run)
- [ ] #2 The nightly workflow runs the whole backend suite at the ci profile (2,000 examples), besides its existing 50k and exhaustive jobs
- [ ] #3 The suite passes under xdist locally and in CI (no test depends on order or shared state); make test uses xdist too
- [ ] #4 pr-workflow, ci docs, CLAUDE.md and the README describe the new split; step names and the test.yml timeout/comment are accurate
<!-- AC:END -->
