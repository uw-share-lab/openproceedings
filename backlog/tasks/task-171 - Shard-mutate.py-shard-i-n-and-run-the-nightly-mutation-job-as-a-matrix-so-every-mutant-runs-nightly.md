---
id: TASK-171
title: >-
  Shard mutate.py (--shard i/n) and run the nightly mutation job as a matrix so
  every mutant runs nightly
status: In Progress
assignee: []
created_date: '2026-10-02 10:33'
updated_date: '2026-10-03 01:41'
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

Recovery: diagnose the suite-ci CPU timing failure with paired/interleaved batches and prove the unchanged <8 growth threshold rejects former quadratic scans; integrate the hooks coverage fix after its merge; rerun all eight GitHub shards before checking AC3/4 or completing the task.

Required local gate recovery: move the stable-shard case expression outside command substitution so stock macOS Bash3.2 parses it, preserving the nonempty/nonerror assertion; rerun the table, full tooling and relevant sharding mutants.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Initial proof 37053299707 has seven successful mutation shards and one genuine shard6 survivor (Linux casefold coverage, handled by hooks recovery). suite-ci failed test_unclosed_openers_are_linear[\\(] at ratio8.28. Investigation queued under the shared heavy lock; no threshold/skip changes.

Prepared paired eight-call CPU batches, nine alternating-order rounds and median growth ratio for the LaTeX opener test. Inputs remain2000/8000characters, growth cutoff remains<8, parse-capCPUbudget remains1s. Actual measurements and former quadratic negative controls must pass before committing; perf owns current CPU slot.

Timing evidence under sharedCPUlock: current paired growth4.049418/4.052738/4.043592 for$1/\\(/\\[. Restoring former oracle scans made the ACTUAL edited test fail growth assertion at16.023047/16.016399/15.903574 with unchanged<8cutoff. Original localcheck passed; exactCIhostcondition isunknown, documented transparently. Results and repeatable negativecontrol in docs/results/2026-10-02-mutation-sharding-recovery.md. FocusedCI/reliabilitycheckqueued; AC3/4 staypending correctedGitHubproof.

Focused timing verification passed: 4 tests in2.15s atci profile, 60 actual linearity checks in28.047281416thread CPU seconds; make lint passed. Fulltooling failed pre-existing test-mutate-shard.sh line77 command-substitution case syntax on stock Bash3.2 (32passed/1failed). Fixing the syntax without changing the assertion; no completion claim.

Stable recovery verification: CI-profile test_latex_scan.py: 4 passed in 2.15s; 60 actual positive checks passed in 28.047281416 thread CPU seconds; make lint passed. The unchanged <8 cutoff rejects former closer scans at 16.023047/16.016399/15.903574. Controlled temporal drift made the original estimator report 12.515577 for linear work and the paired estimator 4.063655; this proves susceptibility, not the unknown original CI host cause. Bash portability fix preserves the same assertion: 33/33 rows pass on Bash 3.2.57 and 5.3.9, ShellCheck passes, and fresh full make tooling passes (774 gate rows, 33 sharding rows). Historical learning bodies preserved with dated addenda; INDEX regenerated and checked. Full integration gate and corrected all-eight-shard GitHub proof remain deferred to root after hook merge; AC3/4 stay unchecked, no task completion.
<!-- SECTION:NOTES:END -->
