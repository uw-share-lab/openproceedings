---
id: TASK-167
title: Remove the ~10 ms cost of the synthetic "AI agent$" clause (TASK-076 deferral)
status: Done
assignee: []
created_date: '2026-10-02 09:27'
updated_date: '2026-10-03 01:33'
labels:
  - engine
  - performance
  - deferred
dependencies: []
references:
  - docs/results/2026-10-02-wildcard-phrases.md
  - backend/src/openproceedings/engine/tantivy_engine.py
  - backend/src/openproceedings/engine/compile.py
priority: low
ordinal: 137000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: TASK-076, deferred (docs/results/2026-10-02-wildcard-phrases.md, What stays). The synthetic `"AI agent$"` clause (a phrase with a trailing wildcard, position-verified) still costs about 10 ms per search at 80k after TASK-076's caching. Removing it needs either a reusable id set (tantivy-py 0.26 doesn't expose one, so the verified ids are rebuilt as a term-set query each search) or a per-document fast-field filter, which is a schema change (a new index_version and the index-versioning skill's steps). Not needed for the search budget; filed so the option isn't lost.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Either the engine applies the verified ids through a reusable id set or a per-document fast-field filter (with an index_version bump per the index-versioning skill if the schema changes), or the task is closed with a measured note that the cost no longer matters
- [x] #2 The clause's per-search cost is re-measured at 80k before and after (docs/results/); no ID set, score or count changes (differential, golden)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Serve schemas2/3 without pinned-record regressions; preserve lazy ordinal lookup; measure first/subsequent construction, compile, memo hit, retained memory, and independent collection; verify same-snapshot inputs and all IDs/scores/facets/exclusions before paired timing; regenerate full80k report; run full stable checks then CLI completion.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Schema 3 indexes ord and names verified IDs through an ordinal term set; schema 2 retains text-ID term sets, so pinned indexes remain served. Historical real replay proof: 10/10 records saved on the old code/index reproduced; fresh synthetic contract/schema/differential tests pass. Owner retains exact/replay-safe decision 030 despite no demonstrated end-to-end speedup.

Fresh manifest-verified same-snapshot 80k pair 27659e65468c/83f44f4eb82f: all ten complete ID/float-score orders in all four sorts, facets and exclusions exactly equal before timing. 100-round CPU p50: text construction 3.7 ms / collection 9.7 ms; ordinal first construction 8.2 ms / subsequent 4.7 ms / collection 5.6 ms. Whole-tree compile, verified/expansion memos warm: table first use 25.4 ms / retained 21.8 ms / memo hit 0.1 ms. Retained table 4,162,480 bytes excluding existing strings (object-size estimate, not RSS). 200-round whole warm main-2-pop CPU p50 25.2 ms schema 2 versus 26.0 ms schema 3, wall p95 27.6 versus 27.5 ms: slightly slower median, no demonstrated end-to-end gain. Historical 0–3% and unseparated 11.3→6.2 ms claims are superseded by fresh phase-separated evidence in docs/results/2026-10-02-perf-recovery.md.

Default schema-3 report: every budgeted number within budget under its recorded CPU-idle-qualified baseline; total swap usage increased during the run, limiting wall-time inference. Verified cold queries remain the explicit exception. All cold engine memos reset, including ordinal lookup. Focused checks 99 passed plus four negative manifest-input controls passed. Stable f2b50e3c full make test/lint/tooling passed: backend 6330 passed, 2 skipped; frontend 3209 passed; no lint/tooling errors. Shared lock, Node 22.23.3, four pytest workers; unchanged clean tree throughout. No real indexes/snapshots modified.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Schema 3 uses ordinal verified-ID term sets; schema 2 remains served for pinned replay. Fresh 80k IDs, scores, facets and exclusions agree. Collection 9.7→5.6 ms, construction 3.7→4.7 ms; first-use table adds about 3.6 ms compile cost and 4.16 MB retention. No demonstrated end-to-end speedup. Fresh full report within budget; full test/lint/tooling pass. Owner decision 030 retained; measured limits documented.
<!-- SECTION:FINAL_SUMMARY:END -->
