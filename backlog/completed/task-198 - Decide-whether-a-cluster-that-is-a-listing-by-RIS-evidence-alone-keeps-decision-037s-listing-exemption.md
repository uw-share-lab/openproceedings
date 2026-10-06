---
id: TASK-198
title: >-
  Decide whether a cluster that is a listing by RIS evidence alone keeps
  decision-037's listing exemption
status: Done
assignee: []
created_date: '2026-10-05 20:53'
updated_date: '2026-10-06 00:03'
labels:
  - ingest
  - dedup
milestone: m-4
dependencies: []
ordinal: 142000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the dedup-auditor on 2026-10-05 while reviewing the fix for nightly run 37353576315 (test_dedup_props). Step 3 (abstract_venue_year, TASK-179, decision-037) refuses to merge an import with a record that is no listing and is rejected, withdrawn or desk-rejected; step 2 (`_import_would_take_its_status`) and step 3 (`_abstract_aside`/`_abstract_group`) exempt any listed cluster. `is_listing` also counts a cluster that is a listing only because a RIS row (or an OpenReview note's own urls.proceedings claim) names a proceedings URL. In TASK-174's shape, a rejected OpenReview note, its forum id's RIS row naming a proceedings paper, and an import of that paper with the same abstract merge by abstract, and the merged record keeps `rejected`, because OpenReview outranks RIS for status. `dedup.py:536` reasons that a crawled listing outranks every status claim, which does not hold when the listing is RIS evidence alone. It is no over-merge (both name the same proceedings id), and a crawled proceedings listing, when present, would set the status. The property now asserts the product's current rule (`status in {accepted, unknown} or is_listing`) with this shape as an @example (REJECTED_NOTE_RIS_LISTING).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The owner decides whether a cluster that is a listing by RIS (or a note's own urls) evidence alone keeps the listing exemption in steps 2 and 3, recorded as a decision
- [x] #2 dedup.py and test_dedup_props.py's abstract-merge property follow the decision, with REJECTED_NOTE_RIS_LISTING's expected outcome pinned
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Failing unit tests in test_dedup.py for TASK-174's shape (abstract and title), the crawled-listing and note-own-URL cases, and is_listing unchanged.
2. dedup.py: _Cluster.crawled (listing by crawled evidence: a proceedings source's claim, or a proceedings id in a non-ris urls.proceedings/urls.pdf claim); _import_would_take_its_status, _abstract_aside and _abstract_group test it for decision-037's exemption; is_listing/listed unchanged elsewhere.
3. test_dedup_props.py: the abstract-merge and status properties assert the narrower rule; REJECTED_NOTE_RIS_LISTING pinned as no abstract merge, import accepted.
4. Docs as-built: dedup.py docstrings, spec 01 Pipeline 4, dedup-rules skill, dedup-auditor Musts.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC1: decision-040 (owner, 2026-10-05) records the choice. AC2: dedup.py _Cluster.crawled; _import_would_take_its_status, _abstract_aside, _abstract_group read it; is_listing/listed unchanged. Unit tests in test_dedup.py (TASK-174 shape by abstract and title x 3 statuses; crawled listing present merges accepted; note's own URL still exempt; is_listing unchanged). Props: abstract-merge and status properties assert crawled_listing; REJECTED_NOTE_RIS_LISTING pinned as no merge. Checked: the three new/narrowed property assertions fail on the pre-change dedup.py. Tests: test_dedup.py 210 passed, props 10, ingest unit dir 1637 passed; make tooling green.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
decision-037's status exemption in dedup steps 2 and 3 now counts a cluster as a listing only by crawled evidence (a proceedings source's claim or a non-ris proceedings URL claim), per decision-040. In TASK-174's shape the import of the paper stays a separate accepted record and the rejected note keeps its status; with a crawled listing present the three merge, accepted. is_listing keeps its wider meaning for reconcile and the track rule. Docs as-built: dedup.py docstrings, spec 01 Pipeline 4, dedup-rules skill, dedup-auditor Musts. No snapshot rebuilt (no data/ in the worktree): the effect on the real cache is unmeasured.
<!-- SECTION:FINAL_SUMMARY:END -->
