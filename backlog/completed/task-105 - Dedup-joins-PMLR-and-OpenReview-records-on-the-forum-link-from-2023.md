---
id: TASK-105
title: Dedup joins PMLR and OpenReview records on the forum link from 2023
status: Done
assignee:
  - '@jeevan'
created_date: '2026-09-27 21:34'
updated_date: '2026-09-27 23:11'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 102000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PMLR pages from v202 on carry the OpenReview forum link (v235 stored as the forum URL by TASK-053). Join on it before falling back to the title match.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Records sharing a forum id merge regardless of title differences,Table tests from the fixtures; dedup-rules skill updated
- [x] #2 A forum-id match with contradicting venue/year (or a track the proceedings don't host) is a conflicts.csv row, never a merge
- [x] #3 Property tests: forum-link merge is order-independent, idempotent, and never merges two different forum ids
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. urls.forum_id(): parse an OpenReview forum URL (ingest/urls.py; pmlr.py untouched, TASK-103).
2. dedup: a cluster's forum ids = native forum id + kept urls.forum claims. New step 1b joins step-1 clusters sharing a forum id in the same venue-year, regardless of title, unless they'd hold two forum ids, two proceedings ids or a track the listing doesn't host. merges.csv rule forum_link.
3. Step 2 refuses a title merge whose clusters name two forum ids (native or linked).
4. _refusals: every forum id shared by output records that stayed apart (venue_year_not_merged, or the link refusal).
5. Table tests from v235 + icml-2024 fixtures; property tests; dedup-rules skill, spec 01, record-schema.
6. Dry-run the current snapshot on a scratch copy: records/hash/merges/conflicts unchanged?
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixture check: of the recorded PMLR volumes only v235 carries the OpenReview link (3/3 entries); v28 has none; v220 is a never-ingested NeurIPS competition volume. v202 carrying it is from the research notes, not a fixture.
Built: urls.forum_id(); dedup._link (step 1b, rule forum_link) before the title step; _mergeable counts own+linked forum ids, so a listing linking forum Y never title-merges with note X (a tightening); _refusals reports every forum id (own or linked) shared by records that stayed apart (field forum_id / forum_id_chain). pmlr.py and the OpenReview adapters untouched (TASK-103); record construction needed no change.
Dry run (scratch copies of data/cache + data/snapshots): current snapshot 2026-09-23-d5ab3d6d444a is reproduced byte-identically (records.jsonl, merges.csv, conflicts.csv; 1805 RIS-only records, none a proceedings-id record naming a forum); build reuses it; snapshot_hash, content hashes and index_version a7cfd04b656f unchanged.
Validation: uv run pytest 4055 passed, 2 skipped; make lint 0; make tooling 0.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Dedup now joins records that name the same OpenReview forum id (own id or a kept urls.forum claim, e.g. PMLR v235's index link) in the same venue-year before the title step, whatever their titles (merges.csv rule forum_link). A link across venue-years, to a track the proceedings don't host, or shared by two listings is a conflicts.csv row (field forum_id), never a merge; a title merge that would join two forum ids (own or linked) is refused. Verified by table tests from the recorded v235 index + ICML 2024 note (test_dedup_forum_link.py), unit tests in test_dedup.py, Hypothesis properties (idempotent, order-independent, conservation, never folds two forum ids) with a links() strategy; dedup-rules, record-schema, pmlr-proceedings skills, dedup-auditor and spec 01 updated. Current snapshot unchanged (dry run on copies).
<!-- SECTION:FINAL_SUMMARY:END -->
