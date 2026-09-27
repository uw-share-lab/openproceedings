---
id: TASK-109
title: Warn when a venue-year holds a status its sources cannot supply
status: Done
assignee: []
created_date: '2026-09-27 22:46'
updated_date: '2026-09-27 23:56'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 106000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-082: statuses_indexed also includes any status the records actually hold, which can hide an error in the per-source status table (synthetic data showed ICML 2019 accepted+withdrawn). Log and report such cells instead of silently widening.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Snapshot build reports each unexpected (venue-year, status) with the records behind it,Test with a synthetic record
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
ingest/status_check.py: unexpected_statuses(records, table=expected) returns each (venue, year, status) whose records hold a status none of the venue-year's claim sources can supply (OpenReview v1/v2 every status; NeurIPS proceedings/PMLR accepted only; RIS every status where OpenReview holds the venue-year - v1 adapters with listings, i.e. not ICLR 2015, or v2 years - else accepted), with sources, expected statuses and sorted record ids; logs snapshot_unexpected_status per cell (up to 20 ids, never record text). snapshot.build computes it after dedup and returns it on BuildResult.unexpected_statuses (also for an existing snapshot); op snapshot build prints unexpected_statuses. A report only: the snapshot bytes/hash don't change. The per-source table is a local copy shaped like feat/m3b-ui's ingest/sources.py SOURCE_STATUSES; the table argument is the seam for M3b's statuses_indexed at merge. Spec 01 Pipeline step 5 and the snapshots skill updated. Tests: backend/tests/unit/ingest/test_status_check.py (synthetic ICML 2019 withdrawn RIS record).
<!-- SECTION:FINAL_SUMMARY:END -->
