---
id: TASK-171
title: >-
  Shard mutate.py (--shard i/n) and run the nightly mutation job as a matrix so
  every mutant runs nightly
status: In Progress
assignee: []
created_date: '2026-10-02 10:33'
updated_date: '2026-10-02 18:00'
labels:
  - tooling
  - ci
  - tests
dependencies:
  - TASK-057
references:
  - .claude/scripts/mutate.py
  - .github/workflows/nightly.yml
priority: medium
ordinal: 141000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: TASK-057 (PR #84), 2026-10-02. The full mutation run needs about 6.5 h on 4 CPUs for 548 mutants, over GitHub's 6 h job cap; the 2026-10-02 proof run reached 63 of 548 (all killed) before its 45-minute limit. TASK-057 time-boxes the nightly mutate job at 140 min, which runs only about the first 190 of the 548 mutants, always in the same fixed order, so the rest never run nightly. Add a `--shard i/n` option to .claude/scripts/mutate.py that splits the mutant list deterministically into n disjoint shards covering every mutant, and run the nightly job as a matrix over the shards so every mutant gets nightly coverage within the job cap.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `mutate.py --shard i/n` runs a deterministic, disjoint subset; the n shards together cover every mutant exactly once; a bad value (0/n, i>n, n<1, not i/n) is refused with a clear error
- [x] #2 Case-table rows (in .claude/scripts/tests/, a new table or an existing one) check the partition (disjoint, complete, stable across runs) and the argument errors, with mutants for the sharding logic in a new .claude/scripts/mutants/mutate.json
- [ ] #3 nightly.yml runs the mutate job as a matrix over the shards, each within GitHub's 6 h cap with headroom, and fails if any shard has a surviving mutant; spec 08 §Mutation testing describes it
- [ ] #4 One nightly run (or a manual dispatch) is recorded in the notes with every shard's time and result
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. mutate.py --shard i/n (every n-th selected mutant from the i-th) and --list (labels only); 2. case table test-mutate-shard.sh + mutants/mutate.json; 3. nightly mutate job as an 8-shard matrix (stale pre-check in shard 1, cut-off shard fails); 4. spec 08, ci-engineer, testing-standards as-built; 5. workflow_dispatch proof run
<!-- SECTION:PLAN:END -->
