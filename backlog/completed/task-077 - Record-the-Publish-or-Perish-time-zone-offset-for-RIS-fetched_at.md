---
id: TASK-077
title: Record the Publish or Perish time-zone offset for RIS fetched_at
status: Done
assignee: []
created_date: '2026-09-27 00:05'
updated_date: '2026-10-01 15:12'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 75000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
M2 gate (review-methodologist): the RIS importer takes fetched_at from the M1 Query date, which Publish or Perish writes in the machine's local time; it is stored labelled UTC because the offset isn't recorded, so a crawl date near midnight can be a day off, and PRISMA-S keeps search and crawl dates apart. Record the offset (an ingest option or the cache's metadata) and convert, or mark such claims 'local, offset unknown'.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 fetched_at from a RIS import is either converted with a recorded offset or explicitly marked local
- [x] #2 The snapshot manifest's crawl window says which
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Offset recovered from Publish or Perish's own query records (epoch seconds), matching a RIS query date to the second for each search: both -04:00. Owner decisions 2026-10-01: evidence accepted, convert to UTC, decision-025 accepted. Snapshot rebuild is left to the owner after merge (new snapshot_hash and index_version; existing records replay drifted, membership-identical).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
fetched_at from a RIS import is converted to UTC with the offset backend/src/openproceedings/ingest/ris_offsets.toml records per cache entry (out-covidence and out-covidence-2020-2024 at -04:00, with evidence); an entry not in the table keeps its local wall time and its ImportReport.utc_offset is null. The snapshot manifest records each report's utc_offset and a new additive key query_dates {ris: utc|local}; crawl_dates_kind gains scholar_query_dates_utc and mixed_utc (open set), derived the same way by records.snapshot_facts and coverage.breakdown. The record page, methods text and CLI say '(local time)' only for the local kinds. Decision-025 (accepted) records the choice and the reproducibility effect. Specs 01/04/05, the copy deck RC-9, the prisma-reporting, search-records and snapshots skills, the ris-importer agent and CLAUDE.md updated. The owner rebuilds the snapshot after merge.
<!-- SECTION:FINAL_SUMMARY:END -->
