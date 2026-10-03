---
id: TASK-072
title: >-
  Reconcile OpenReview acceptance against crawled proceedings (decision-005
  status rule)
status: Done
assignee: []
created_date: '2026-09-26 16:35'
updated_date: '2026-09-30 00:09'
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
1. ingest/reconcile.py: crawled proceedings (source, venue, year) from the listing reports, complete only when every listing states a count and matches it, every entry became a record (duplicates aside), it names no uncrawled volume (see_also) and it was read; the tracks each covers from its listing records (a listing's own unknown track: the track of the record it merged into), limited to main/D&B/position.
2. reconcile(result, crawled): an OpenReview-accepted record (status won by openreview_v1/v2) in a covered venue-year-track that is not a listing (dedup.is_listing) and shares no title key or forum id with one gets a status=unknown claim from the proceedings source (url: the listing holding the track, fetched_at: that listing's index-page fetch, evidence: not listed: ...); resolve() then gives unknown and a precedence:<source> conflicts.csv row.
3. dedup: an absence claim (a proceedings status=unknown claim whose evidence starts 'not listed:') is not a listing: excluded from a cluster's sources, so re-running dedup and reconcile changes nothing.
4. snapshot.build runs it after dedup; logs one summary line.
5. Unit + property tests (idempotence, dedup fixed point, only unlisted OR-accepted records change, incomplete listing and uncrawled track do nothing).
6. Real-data check on the TASK-126 scratch cache; measure the track-precedence note before enforcing it.
7. Docs: decision-005, dedup-rules skill, record-schema skill, spec 01, results note.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From the M2 gate (dedup audit): dedup.py's precedence lets proceedings answer track in a venue-year that is on OpenReview when no OpenReview claim is present; decision-005 says proceedings answer only for venue-years not on OpenReview. Unreachable until the crawlers (task-052/053); enforce it when reconciling.

## As built
ingest/reconcile.py, run by snapshot.build after dedup (before with_crawl_conflicts).
- Crawled = (proceedings source, venue, year) whose every ListingReport was read, states a count (stated is not None) and matches it (count_ok), has records + skipped.duplicate == listed, and names no uncrawled volume (see_also). One incomplete listing leaves the venue-year alone (WARNING proceedings_reconcile_skipped).
- Covered tracks = main/D&B/position held by that crawl's listing records (own track claim; a mixed PMLR volume's unknown -> the merged record's track).
- Unlisted = status won by OpenReview accepted, not a listing (dedup.is_listing: a proceedings claim or a proceedings id in urls.*), no shared title key or forum id with any listing of the venue-year (shares -> left alone, counted).
- Such a record gains an absence claim: status=unknown from the proceedings source, the listing holding the track as url, that listing's index-page fetch (ListingReport.fetched[0]) as fetched_at, evidence 'not listed: ...' (prefix reserved, record-schema skill). resolve gives unknown + the precedence:<source> conflicts row. dedup.is_absence keeps absence claims out of a cluster's sources, so dedup on the output is a fixed point; reconcile strips absence claims before judging (idempotent; stale ones drop).
- Reconcile imports dedup.PROCEEDINGS_SOURCES / PROCEEDINGS_TRACKS / is_listing (no copies). ICLR archive counts as official proceedings (decision-005 names it); no-op on real data.
- Track-precedence row NOT enforced: measured, left to the lead (TASK-130).
- Not done (schema change): Reconciled counts in the snapshot manifest; a new manifest key needs a snapshot FORMAT_VERSION bump (verify requires format_version == FORMAT_VERSION) and render() takes DedupResult. The counts are in the proceedings_reconciled / proceedings_reconcile_skipped log lines.

## Real data (current; after TASK-128)
TASK-126 cache (read-only), snapshot 2026-09-29-4cd2bba17cad, index b170674bcf49 (docs/results/2026-09-29-reconcile-real-data.md). proceedings_reconciled: crawls 29, unlisted 4, shares_listing 0, incomplete 1 (NeurIPS 2021 skipped as incomplete: its D&B page states no count, though 174 = 174 records = 174 official; the conservative rule is kept by the lead).
- Made unknown: NeurIPS 2023 D&B 3sRR2u72oQ (INSPECT, renamed) and pTSNoBTk8E (DynaDojo, renamed), 2024 main ftqjwZQz10 (DEX, truly absent), 2025 D&B mORzRZaqT4 (GuardSet-X, listed as PolyGuard). Cells 2023 D&B 324->322, 2024 main 4035->4034, 2025 D&B 498->497: all equal official.
- M4 gate PASS: 43/44 within 1%, plus ICLR 2013 main as the owner-accepted exception (decision-016).
- Track row: 149 records get a proceedings-only track in an OpenReview venue-year; enforcing would move ICLR 2016 main 80->0 and ICLR 2014 main 35->34 (-2.9%).

## Superseded: first run, before TASK-128 (kept for the record)
Snapshot 2026-09-29-eb72536c21d1, index b2a358e2f955, under the round-0 completeness rule: 6 unknown, 1 shares_listing (NeurIPS 2021 main), 0 incomplete; also NeurIPS 2023 main 3219->3218 and 2025 main 5287->5286, whose listings' titles html.py had mangled (charref ';' dropped, TASK-128). Gate FAIL 43/44 (before decision-016). Track row 151. Rebuild 2026-09-29-7fd4c937496e (round-1 rule) differed only in the absence claims' fetched_at.

## Reviews
Round 1 (REQUEST_CHANGES), fixed: stated/see_also completeness; public dedup sets and is_listing; tests for an ambiguous cross-track title, a refused forum link, an unknown-track listing, the stated/see_also/unread rows and the absence claim's own fetch time (each killed its breakage); fetched_at from the listing's index page; TASK-128/TASK-130 links; results note; record-schema reserved prefix; dedup-rules known limit (papers moved between years).
Round 2 (approved), fixed: a reconcile test for a note that is a listing only through a urls.proceedings id (fails with a source-only check at either is_listing call site); miner tests pinning report.fetched[0] as the index page's fetch (iclr, neurips, pmlr); these notes and the plan made as-built.

Docs: decision-005, dedup-rules skill §Reconcile, record-schema skill, spec 01 Pipeline 4 + Error handling + Testing, CLAUDE.md layout, docs/results/2026-09-29-reconcile-real-data.md.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Built decision-005's reconcile step (ingest/reconcile.py, run by op snapshot build after dedup): where a venue-year's official proceedings are crawled completely, an OpenReview-accepted paper that no listing holds and that shares no title or forum id with one gets an absence claim (status=unknown from the proceedings source, listing URL, the listing's index-page fetch, evidence 'not listed: ...') and a precedence conflicts.csv row. Absence claims never make a record a listing, so dedup and reconcile are fixed points. On the real crawl after TASK-128 (snapshot 2026-09-29-4cd2bba17cad) it makes 4 records unknown (3 renamed camera-readies, 1 truly absent), every NeurIPS gated cell equals official, and the M4 gate passes (43/44 plus the ICLR 2013 exception). NeurIPS 2021 is skipped because its D&B page states no count. Follow-ups: TASK-130 (decision-005 track row, measured at 149 records, not enforced). Manifest counts deferred: they need a snapshot format bump.
<!-- SECTION:FINAL_SUMMARY:END -->
