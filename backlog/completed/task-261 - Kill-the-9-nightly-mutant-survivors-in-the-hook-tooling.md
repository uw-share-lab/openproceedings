---
id: TASK-261
title: Kill the 9 nightly mutant survivors in the hook tooling
status: Done
assignee: []
created_date: '2026-10-18 14:16'
updated_date: '2026-10-19 11:49'
labels:
  - tooling
  - mutation
  - release
dependencies: []
priority: high
ordinal: 174000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the v0.4.0 release (2026-10-18, spec 08 §Release step 1): the scheduled nightly has been red since 2026-10-15 (runs 38736208920, 38900169100, 39029318530), only in its mutate shards, each failure a deterministic surviving mutant. Red since #149/#150 (between 855749a3 and 79c269fe); four more since #158. Survivors: 'pdd: find checks only its first start'; 'TASK-243: the two walks compared as one'; 'block-ai: HOME '' pass skipped (TASK-156)'; 'block-ai: a glob in a file word isn't expanded (TASK-170)'; 'cmdparse: an inherited HOOK_INPUT read in place of stdin (TASK-156)'; 'PR gate: aliases not expanded'; 'PR gate: git-<sub> behind an unknown wrapper loses its subcommand'; 'PR gate: git not basenamed'; 'PR gate: git-<sub> token skipped'. Not covered by TASK-253 or TASK-254. Blocks v0.4.0.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each of the 9 mutants is killed by a case-table row that fails on the message it asserts, or recorded as equivalent with the reason in the mutant file
- [x] #2 mutate.py on each affected shard (at --jobs 2) reports no survivors locally
- [x] #3 A nightly dispatched on the merged head is green
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Reproduce each survivor locally with one table per mutant. 2. Find why the existing rows stopped killing it. 3. Add or correct rows so each one fails under its mutant and passes on the code. 4. Run mutate.py --match per mutant at --jobs 2. 5. Review gate, PR, merge queue. 6. Dispatch a nightly on the merged dev head (AC #3).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-18: each survivor reproduced locally, one table per mutant. Causes:
- the 4 PR-gate mutants: their rows used caffeinate, which TASK-248 made a known wrapper, so git_calls' fallback went untested; new rows go behind 'unknown-wrapper';
- HOOK_INPUT: '{}' is refused as malformed by guard_payload either way; new rows use a well-formed harmless HOOK_INPUT;
- block-ai HOME '' pass: with the real HOME the first reading refused the missing op-msg.txt (TASK-243); HOME now holds a clean one;
- glob: a glob matching a trailer file is refused unexpanded too; a new row globs a clean file (allow);
- TASK-243 two walks: a new row writes the sent file only in the HOME '' walk;
- pdd find: killed on macOS, but on Linux the mktemp root is under /tmp, so 'find /tmp .' blocked on its first start; the row is now 'find src .'.
Each mutant fails exactly its new row (scratch single-table runs). The caffeinate rows stay as regression rows: they cannot tell the walk unwrapping from the git_calls fallback, and the TASK-248 rows kill the known-wrapper mutants. make lint and make tooling are green.

2026-10-18: mutate.py --jobs 2, one --match at a time, 0 problems for each:
- 'PR gate: git': 4 mutants;
- 'PR gate: aliases': 1;
- 'pdd: find checks only': 1;
- 'two walks': 1;
- 'pass skipped': 2, including require-review's;
- 'glob in a file word': 1;
- 'inherited HOOK_INPUT': 1.
AC #1's 'the message it asserts' is the row's asserted verdict (exit 2 or 0). The case tables don't capture stderr, and each new row's other inputs are made harmless, so only the check under test decides the verdict. The AC wasn't reworded, because the CLI would renumber AC #3.
Review round 1 (code, docs, security, QA): no Must. Fixed:
- git_calls' docstring example;
- positive controls for the data-only find row and the two-walks row;
- a sibling absolute find start;
- xargs mv -t /tmp → frontend (on Linux /tmp is above the table's repo);
- relabels.

AC#3: nightly 39221205207 on b24060b8 (contains edc6d5b5) passed every job; the earlier 39191247944 failed only on a shard timeout (TASK-265), with no survivors.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The nine nightly survivors are killed by case-table rows; a nightly on the merged head is green.
<!-- SECTION:FINAL_SUMMARY:END -->
