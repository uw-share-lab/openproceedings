---
id: TASK-154
title: >-
  Nightly: reconcile property finds an unexpected conflict for an unlisted
  OpenReview acceptance
status: Done
assignee: []
created_date: '2026-10-01 05:26'
updated_date: '2026-10-01 05:32'
labels:
  - dedup
  - bug
dependencies: []
priority: high
ordinal: 130000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The nightly suite-ci job (2,000 examples, run 36723434594 on 2026-09-30) failed on backend/tests/unit/ingest/test_reconcile.py::test_only_unlisted_openreview_acceptances_change_and_only_to_unknown (AssertionError at test_reconcile.py:329: reconcile returned a Conflict the property says it shouldn't). It reproduces deterministically on dev 49fd6e0 with @reproduce_failure('6.168.1', b'AXicc2R0ZHAEYQZGR0YGRyhkgAgwYEJGRyYgZGSAaIJrZgAAMQ0ILw=='); the input involves a NeurIPS 2024 proceedings listing (tracks {'main'}, complete=True). Nightly stays red until either reconcile or the property's oracle is fixed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Root cause found and recorded: whether reconcile or the property/oracle is wrong
- [x] #2 The wrong side is fixed, or the options are reported to the owner if the fix changes documented behaviour
- [x] #3 The failing input is an explicit @example on the property, independent of the Hypothesis blob
- [x] #4 The property passes at the nightly profile (2,000 examples)
- [x] #5 If reconcile code changes, a replay of the real crawl shows reconcile and coverage counts unchanged or explained
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Reproduce from the blob; decide code vs oracle against decision-005, spec 01 and the dedup-rules skill; pin the input as an explicit @example; fix the wrong side; mutation-check; check the real snapshot.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Root cause: the property's oracle, not reconcile. The shrunk input (an ICLR 2024 crawl whose one listing has the NeurIPS LISTING constant as its URL, hence 'NeurIPS 2024 listing') has a note op:iclr:2024:IjKl9012 whose v2 claim says accepted and whose v1 twin (same id, a pool record) says rejected: dedup writes a precedence:openreview_v2 status row. Reconcile makes the note unknown and, as designed since TASK-072, replaces a changed record's precedence status rows with the ones its claims now resolve to (unknown over accepted/v2 and unknown over rejected/v1). The oracle's last line, 'rows are only added', missed that. Keeping the stale row instead would break decision-005 (the record equals what its claims resolve to and the precedence row is its conflicts.csv row), spec 01 and the documented 'dedup on the output changes no row' property, so the code is right; the skill's 'conflicts only gain the reconciled records' status rows' was the imprecise sentence. Not a TASK-137/139/142/147 regression: the oracle line, the v1 source in the strategy and the replace logic all date from c28628c (TASK-072); 2,000 examples were needed to reach a same-id v1 twin with another status.
Fix: the oracle now allows only a changed record's superseded precedence status rows to go, and requires every non-unknown value they named to stay named against unknown; NIGHTLY_154 is the exact shrunk input (checked equal to the blob's) as @example; a table test pins the rows. Mutation check: two reconcile mutants (drop one fresh row; drop unchanged records' status rows) are each killed. Real data (read-only, snapshot 2026-09-29-333bf918c9b3): 4 reconciled records, none with a second OpenReview status value, so the case never occurs there; reconcile code is unchanged, so no replay was needed.

Validation: HYPOTHESIS_PROFILE=ci uv run pytest backend/tests/unit/ingest/test_reconcile.py -> 19 passed in 99.91s. Without the oracle fix the @example alone fails at the same assertion as nightly.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Nightly's reconcile counterexample was an oracle bug, not a reconcile bug: a note whose OpenReview v2 and v1 claims disagree has a v2-over-v1 status row, and reconcile rightly replaces a demoted record's status rows with what its claims now resolve to (decision-005; dedup on the output changes no row). The property now allows exactly that and checks every superseded value is still named against unknown; the shrunk input is an explicit @example (NIGHTLY_154) and a table test pins the rows; the dedup-rules skill's 'conflicts only gain' sentence is corrected. Reconcile code unchanged; the real 2026-09-29 snapshot has no record in this case (4 reconciled, none with a second OpenReview status). Verified at the ci profile (2,000 examples) and by two killed reconcile mutants.
<!-- SECTION:FINAL_SUMMARY:END -->
