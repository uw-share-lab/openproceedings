---
id: TASK-198
title: >-
  Decide whether a cluster that is a listing by RIS evidence alone keeps
  decision-037's listing exemption
status: To Do
assignee: []
created_date: '2026-10-05 20:53'
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
- [ ] #1 The owner decides whether a cluster that is a listing by RIS (or a note's own urls) evidence alone keeps the listing exemption in steps 2 and 3, recorded as a decision
- [ ] #2 dedup.py and test_dedup_props.py's abstract-merge property follow the decision, with REJECTED_NOTE_RIS_LISTING's expected outcome pinned
<!-- AC:END -->
