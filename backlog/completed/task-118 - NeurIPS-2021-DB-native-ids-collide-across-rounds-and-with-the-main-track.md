---
id: TASK-118
title: NeurIPS 2021 D&B native ids collide across rounds and with the main track
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 05:29'
updated_date: '2026-09-29 05:39'
labels:
  - ingest
  - bug
milestone: m-4
dependencies: []
priority: high
ordinal: 114000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The NeurIPS proceedings path hash is md5(str(paper number)). The 2021 Datasets & Benchmarks site (datasets-benchmarks-proceedings.neurips.cc) numbers round 1, round 2 and the main track independently, so different papers share a hash and therefore the native id nips-<hash>. The first live dry run (2026-09-29) listed 174 D&B 2021 entries (matching the official 174) but skipped 54 as 'duplicate': 27 repeat across rounds and 27 collide with 2021 main-track papers, and 0 of 54 share a title. A live crawl would index 120 of 174 (-31%) and fail the M4 gate (TASK-054).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 D&B 2021 round papers get a round-qualified native id (nips-<hash>-round1/-round2); main-track and 2022+ ids are unchanged
- [x] #2 The record-id pattern, urls.native() and the miner agree on the new form, and a URL round-trips to the same id
- [x] #3 A recorded-fixture regression test fails on the old behaviour: two different papers sharing a hash across rounds and with the main track are all kept
- [x] #4 Spec 01, the record-schema and neurips-proceedings skills describe the new id form
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Fixed via urls.proceedings_native (one id rule for the miner, RIS and dedup). Live dry run after the fix: 2021 D&B listed 174, planned 174, skipped none (was 120 planned, 54 'duplicate'). A D&B link without round1/round2 is skipped as no_round (miner) / unresolved (RIS).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
NeurIPS 2021 D&B papers now get round-qualified native ids (nips-<hash>-round1/-round2) from one function, urls.proceedings_native, used by the miner, the RIS importer (whose ambiguity check now keys on the native id) and dedup; the record pattern accepts exactly that form. Main-track and 2022+ ids are unchanged. Live dry run: 2021 D&B planned 174/174 (was 120, 54 false duplicates). Tests: new test_urls.py, a derived-fixture miner regression and a RIS main/D&B ambiguity case; make test 5139 passed, 2 skipped; frontend 2582 passed; make lint clean.
<!-- SECTION:FINAL_SUMMARY:END -->
