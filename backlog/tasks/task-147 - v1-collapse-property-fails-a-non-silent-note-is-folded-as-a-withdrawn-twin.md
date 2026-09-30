---
id: TASK-147
title: 'v1 collapse property fails: a non-silent note is folded as a withdrawn twin'
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 13:44'
labels:
  - decision
  - bug
milestone: m-4
dependencies: []
references:
  - backend/tests/unit/ingest/test_openreview_v1_collapse_props.py
  - backend/src/openproceedings/ingest/sources/openreview_v1.py
documentation:
  - >-
    backlog/decisions/decision-020 -
    OpenReview-v1-status-signals-that-disagree-stay-unknown-including-a-withdrawn-twin-of-an-accepted-note-TASK-113.md
priority: high
ordinal: 124000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found 2026-09-30 while filing follow-ups (an earlier session had seen this test "flake"). `backend/tests/unit/ingest/test_openreview_v1_collapse_props.py::test_a_collapse_never_folds_two_papers_or_loses_an_acceptance` fails deterministically on dev (08baa08) with `@reproduce_failure('6.168.1', b'AXicc2R1ZHZkdGRxZHVkAtIQyIAGIaJMOMTBbABZUQlF')`: `AssertionError: op:neurips:2021:Zz0Note3` at line 117, `assert silent_note(listings, gone) and gone.status == "unknown"`, where `silent_note` is False. So the crawl dropped a note that was not silent and not identical to its kept twin, which the property says only rule 5's silent-twin collapse (`collapse_silent_twins`, TASK-132) may do. Either the collapse changes from TASK-139 (PR #45, commit ed30f73: both collapses skip a record with a crawl conflict or one the withdrawn-twin rule touched; decision-020) fold a note they should not, or the test's oracle no longer matches the rules decision-020 records. High priority: a wrong collapse can fold two papers into one record or lose an acceptance, which moves the reported counts.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The cause is found and written in the task notes: a bug in `ingest/sources/openreview_v1.py`'s collapse (rule 5 or `collapse_silent_twins`) or in the property's oracle, checked against decision-020 and the TASK-139 rules
- [ ] #2 The fix is made where the cause is (code, or the oracle with decision-020 as its reference); if the rule itself changes, decision-020 and the openreview-venueids/dedup docs say so
- [ ] #3 This input is pinned as an `@example` regression on the property (the example the reproduce_failure blob decodes to), and the property passes under the `pr` and `ci` profiles
- [ ] #4 The real crawl's collapse counts (duplicate_submission and silent-twin counts per venue-year, replayed from the cached 2026-09-29 crawl) are unchanged, or each change is listed and explained
<!-- AC:END -->
