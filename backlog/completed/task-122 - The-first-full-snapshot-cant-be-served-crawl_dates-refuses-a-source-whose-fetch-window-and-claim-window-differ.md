---
id: TASK-122
title: >-
  The first full snapshot can't be served: crawl_dates refuses a source whose
  fetch window and claim window differ
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 19:14'
updated_date: '2026-09-29 19:16'
labels:
  - api
  - bug
milestone: m-4
dependencies: []
priority: high
ordinal: 111000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A trial of TASK-054 part 2 on the 2026-09-29 crawl (96,601 records) built a snapshot and index, but op eval coverage refused: 'the snapshot manifest gives a source two crawl windows'. The manifest records openreview_v2's window twice with different meanings: sources[].crawl_window spans every response fetched (the /groups calls came first, at 06:09:01Z) while format 2's crawl_windows spans the claims on records (the first at 06:10:05Z). coverage.crawl_dates and records.snapshot_facts both required them equal, so the API could not load the index's coverage nor save a search record on it. Spec 04 defines a record's crawl_dates per source from format 2's crawl_windows.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 coverage.crawl_dates and records.snapshot_facts take per-source windows from crawl_windows when the manifest has them (format 2), and from sources[].crawl_window only when it has none (format 1); a source named * is still refused
- [x] #2 A regression with a fetch window wider than the claim window is served (coverage and a search record), and the two functions agree
- [x] #3 The trial snapshot of the live crawl passes op eval coverage
- [x] #4 Spec 04 and the snapshots skill say which window crawl_dates uses and what the other one is for
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
coverage.crawl_dates and records.snapshot_facts now take a source's window from format 2's crawl_windows (the claims on records, spec 04) and fall back to its sources entry's crawl_window (every response fetched) only when it has no claim window, instead of refusing when the two differ. They differ by design: the live 2026-09-29 openreview_v2 crawl fetched /groups at 06:09:01Z before its first note at 06:10:05Z. That refusal made the first full snapshot (96,601 records) unservable: the API computes coverage when it loads an index, and a search record's facts ran the same check. A source named * is refused by both alike. A regression test for each; the refusal row that encoded the bug was removed. The trial snapshot now passes op eval coverage (35 of 44 gated cells within ±1%).
<!-- SECTION:FINAL_SUMMARY:END -->
