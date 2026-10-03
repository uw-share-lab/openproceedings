---
id: TASK-147
title: >-
  v1 collapse property fails: a note rule 5 folds into a silent twin is then
  folded into the accepted note
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 13:44'
updated_date: '2026-09-30 14:16'
labels:
  - dedup
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
Found 2026-09-30 while filing follow-ups (an earlier session had seen this test "flake"). `backend/tests/unit/ingest/test_openreview_v1_collapse_props.py::test_a_collapse_never_folds_two_papers_or_loses_an_acceptance` fails deterministically under `@reproduce_failure('6.168.1', b'AXicc2R1ZHZkdGRxZHVkAtIQyIAGIaJMOMTBbABZUQlF')` on dev (08baa08, and still on ba57c68); random runs usually pass, so it can flake the required `test` job on unrelated PRs. The error is `AssertionError: op:neurips:2021:Zz0Note3` at line 116, `assert silent_note(listings, gone) and gone.status == "unknown"`, where the test's oracle `silent_note` (test file :83) is False.

The falsifying input (reproduced by the reviewer): five notes, all on NeurIPS 2021 Blind_Submission, with no Withdrawn listing. Three share content ("Another synthetic title.", same pdf): Zz0Note3 has `venue: ''` (an empty string, so not silent to either the code's `_says_nothing_of_status` or the oracle), Zz4Note2 has no venue key (silent), and Zz2Note4 has `venue: 'NeurIPS 2021 Poster'` (accepted). The report shows withdrawn_by_twin=0, no conflicts and duplicate_submission=3. The kept records are Note1 (unknown) and Note4 (accepted). The mechanism is a chain in the crawl (`openreview_v1.py` ~768-773): rule 5 (`collapse_duplicate_submissions`) folds Note3 into its identical twin Note2 (both unknown), then `collapse_silent_twins` (TASK-132) folds Note2 into the accepted Note4, so Note3's identical survivor is gone. (The third drop: rule 5 folds Zz3Note5 into its identical twin Note1, "Synthetic title text 14.", neither with a venue key.) No paper is split or merged wrongly and the acceptance is kept; what's in question is whether a rule-5 survivor that absorbed a non-silent note may still count as silent. TASK-139's withdrawn-twin changes (PR #45, ed30f73) and decision-020 are context only: nothing here is withdrawn. Priority High because a required CI job can fail on unrelated PRs, and because the collapse rules decide which records exist.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The cause is decided and written in the task notes, checked against decision-020 and the module docstring's rule 5: either the code is wrong (a rule-5 survivor that absorbed a non-silent note is not silent, so `collapse_silent_twins` must skip it) or the oracle is (a chained rule-5 then silent-twin collapse is allowed, and the property says so)
- [x] #2 The fix is made where the cause is; if the rule itself changes, decision-020 and the openreview-venueids and dedup-rules skills say so
- [x] #3 This input (the five notes above, written out in the test rather than decoded from the blob) is pinned as an `@example` regression on the property, and the property passes under the `pr` and `ci` profiles
- [x] #4 The real crawl's collapse counts (duplicate_submission per venue-year) are unchanged, or each change is listed and explained: counted before and after by replaying the cached v1 crawl files (`data/cache/openreview/v1/crawls/<Venue>-<Year>.json`, the 2026-09-29 crawl) offline with the v1 `replay` step that `op snapshot build` runs (openreview-api skill)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Pin the five notes as an @example and a direct test (red). 2. Decide code vs oracle against rule 5, decision-020, decision-005. 3. Fix where the cause is (green). 4. Replay the cached v1 crawls before and after. 5. Docs, full make test, lint, tooling.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Cause (AC#1): the code is wrong, not the oracle. Rule 5 in the module docstring defines a silent twin as a note that says nothing of its status, and says a second record with evidence makes the group a choice, so nothing is removed. Before rule 5 this paper has three notes: Note2 (silent), Note3 (`venue: ''`: a key, so not silent to `_says_nothing_of_status` either) and the accepted Note4. The crawl dropped Note3 into Note2 by rule 5, then folded Note2 into Note4 as a silent twin, although Note2 now stood for a note with a venue key. The outcome also turned on rule 5's tie-break alone: with Note3 numbered lower, rule 5 keeps Note3, which is not silent, and the silent-twin pass leaves the paper as two records. A rule whose result depends on an arbitrary tie-break is not the documented rule, so accepting the chain in the oracle would bless order dependence. Fix: after rule 5, a survivor that absorbed a non-silent note leaves `silent` (openreview_v1.crawl). Checked against decision-020 (withdrawn twins: nothing here is withdrawn, and the fix only keeps a record the rule would have removed; the rule never changes a status) and decision-005 (disagreements are kept visible, never silently resolved: the fix keeps one more `unknown` record, the safe direction, a possible duplicate rather than a fold). No rule changes, so decision-020 is unchanged; the module docstring, spec 01, and the openreview-api and dedup-rules skills now say a rule-5 survivor is silent only if every note it stands for is.

AC#4 replay: every cached v1 crawl in the main checkout's data/cache/openreview/v1/crawls (13 files, 2026-09-29 crawl) replayed offline with openreview_v1.replay before and after the fix. Identical: per venue-year imported, duplicate_submission, unknown_status, track×status and the record id set. Only NeurIPS 2021 collapses: duplicate_submission 301 (300 by rule 5, 1 silent twin W6e384Lkjbw into rDdb26AQ0SO), imported 2,719; every other venue-year 0. W6e384Lkjbw absorbed no note by rule 5, so the fix doesn't reach it.

Tests: the property passes under HYPOTHESIS_PROFILE=pr and =ci (and 3 more ci seeds); with the fix stashed, the new @example and the direct test fail (red), with it they pass.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The v1 crawl folded a rule-5 survivor into its accepted twin as silent even when the survivor had absorbed a note with a venue key, so rule 5's number tie-break decided whether the silent-twin collapse ran. The code was wrong (rule 5: a second record with evidence makes the group a choice); the crawl now drops a survivor from `silent` when it absorbed a non-silent note. The five-note input is pinned as an @example and a direct test (including the numbers swapped). The property passes under the pr and ci profiles. Replay of all 13 cached v1 crawls is unchanged (NeurIPS 2021 duplicate_submission 301, all else 0). make test (5,844 backend, 3,033 frontend), make lint and make tooling pass. Docs: module docstring, spec 01, openreview-api and dedup-rules skills.
<!-- SECTION:FINAL_SUMMARY:END -->
