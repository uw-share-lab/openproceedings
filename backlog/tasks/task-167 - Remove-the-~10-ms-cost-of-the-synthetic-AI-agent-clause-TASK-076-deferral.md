---
id: TASK-167
title: Remove the ~10 ms cost of the synthetic "AI agent$" clause (TASK-076 deferral)
status: In Progress
assignee: []
created_date: '2026-10-02 09:27'
updated_date: '2026-10-03 01:26'
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
Schema3 indexes ord; schema2 retains text-id term sets so pinned records remain reproducible. Historical10/10 real pinned records replayed reproduced; fresh contract/schema/differential checks run on immutable synthetic indexes. Same-snapshot verified manifest pair27659e65468c/83f44f4eb82f: all10 whole ID/float-score orders every4sorts/facets/exclusions equal.100round phase-separated CPU p50: text construction3.7ms/collection9.7ms; ordinal first construction8.2ms/subsequent4.7ms/collection5.6ms; whole-tree compile verified/expansion warm first lookup25.4ms/retained21.8ms/memo hit0.1ms. Retained table4,162,480bytes excluding existing strings, not RSS.200round whole warm main2 CPU p50 25.2ms(schema2) versus26.0ms(schema3), wall p95 27.6 versus27.5ms: no demonstrated E2E gain, slightly slower median. Historical0-3% and11.3->6.2 claims superseded by phase-separated evidence docs/results/2026-10-02-perf-recovery.md. Full schema3 report every budgeted number within budget under explicit CPU-idle-qualified baseline and memory pressure; cold verified queries are exceptions. Owner retains exact/replay-safe schema decision030. Focused99passed plus input-guard4passed; full stable checks pending. No real indexes/snapshots modified.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Schema3 applies verified IDs as ordinal term sets; schema2 remains served for pinned replay. Fresh paired80k membership/scores/facets/exclusions equal; collection9.7->5.6ms but construction3.7->4.7ms, first lookup adds~3.6ms compile/4.16MB retained. No demonstrated E2E speedup. Fresh report within budget; full stable checks pending before terminal status.
<!-- SECTION:FINAL_SUMMARY:END -->
