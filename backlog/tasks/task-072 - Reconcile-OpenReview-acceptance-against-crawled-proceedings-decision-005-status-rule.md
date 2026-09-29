---
id: TASK-072
title: >-
  Reconcile OpenReview acceptance against crawled proceedings (decision-005
  status rule)
status: In Progress
assignee: []
created_date: '2026-09-26 16:35'
updated_date: '2026-09-29 23:12'
labels:
  - ingest
milestone: m-4
dependencies:
  - TASK-021
  - TASK-052
  - TASK-053
ordinal: 71000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-005: where a venue-year's official proceedings are published and crawled, an OpenReview-accepted paper they don't list gets status=unknown plus a conflicts.csv row. Dedup can't decide it alone: it needs the crawled proceedings venue-years from the NeurIPS/PMLR miners. Found in the task-021 review (2026-09-26).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A reconcile step after dedup takes the crawled proceedings venue-years (from task-052/053 manifests) and sets unknown + a conflicts.csv row for OpenReview-accepted, unlisted papers
- [x] #2 The derived status is a claim with its evidence, so dedup's inputs-equal-their-claims check and idempotence still hold
- [x] #3 Unit and property tests; dedup-rules skill and decision-005 updated
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. ingest/reconcile.py: crawled proceedings (source, venue, year) from the listing reports, complete only when every listing's stated count matches and every entry became a record (duplicates aside); the tracks each covers from its listing records (a listing's own unknown track: the track of the record it merged into), limited to main/D&B/position.
2. reconcile(result, crawled): an OpenReview-accepted record (status won by openreview_v1/v2) in a covered venue-year-track that is not a listing and shares no title key or forum id with one gets a status=unknown claim from the proceedings source (url: the listing, fetched_at: the crawl's last fetch, evidence: not listed); resolve() then gives unknown and a precedence:<source> conflicts.csv row.
3. dedup: an absence claim (a proceedings status claim of unknown) is not a listing: excluded from a cluster's sources, so re-running dedup and reconcile changes nothing.
4. snapshot.build runs it after dedup; logs one summary line.
5. Unit + property tests (idempotence, dedup fixed point, only unlisted OR-accepted records change, incomplete listing and uncrawled track do nothing).
6. Real-data check on the TASK-126 scratch cache; measure the track-precedence note before enforcing it.
7. Docs: decision-005, dedup-rules skill, spec 01.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From the M2 gate (dedup audit): dedup.py's precedence lets proceedings answer track in a venue-year that is on OpenReview when no OpenReview claim is present; decision-005 says proceedings answer only for venue-years not on OpenReview. Unreachable until the crawlers (task-052/053); enforce it when reconciling.

Built ingest/reconcile.py, run by snapshot.build after dedup (before with_crawl_conflicts). Crawled = (proceedings source, venue, year) whose every ListingReport has count_ok and records + skipped.duplicate == listed; one incomplete listing leaves the venue-year alone (WARNING proceedings_reconcile_skipped). Covered tracks = main/D&B/position held by that crawl's listing records (own track claim; a mixed PMLR volume's unknown -> the merged record's track). Unlisted = status won by OpenReview accepted, not a listing (dedup's notion: proceedings claim or proceedings id), no shared title key or forum id with any listing of the venue-year (shares -> left alone, counted). Such a record gains an absence claim (status=unknown from the proceedings source, listing URL, crawl's last fetch, evidence 'not listed: ...'); resolve gives unknown + the precedence:<source> conflicts row. dedup.is_absence keeps absence claims out of a cluster's sources, so dedup on the output is a fixed point; reconcile strips absence claims before judging (idempotent; stale ones drop). ICLR archive counts as official proceedings (decision-005 names it); no-op on real data.
Track-precedence note NOT enforced (stop condition): 151 real records have a proceedings-won track in an OpenReview venue-year; setting them unknown would move ICLR 2016 main 80->0 and ICLR 2014 main 35->34 (-2.9%), outside the gate in the wrong direction. Recorded as open in decision-005.
Real data (TASK-126 cache, snapshot 2026-09-29-eb72536c21d1, index b2a358e2f955): 6 records unknown, 1 shares_listing (NeurIPS 2021 main), 0 incomplete of 29 crawls. NeurIPS 2023 main 3219->3218, D&B 324->322, 2024 main 4035->4034, 2025 main 5287->5286, D&B 498->497: all now equal official. Gate still FAIL 43/44 (ICLR 2013 main, unchanged). snapshot diff: 6 changed (status only), merges.csv identical; dedup of the new records is a fixed point. 5 of 6 are listed under another title (3 renamed, 2 mangled by html.py dropping a charref's ';'); only NeurIPS 2024 ftqjwZQz10 (DEX) is truly absent.
Docs: decision-005, dedup-rules skill §Reconcile, spec 01 Pipeline 4 + Error handling + Testing, CLAUDE.md layout.
<!-- SECTION:NOTES:END -->
