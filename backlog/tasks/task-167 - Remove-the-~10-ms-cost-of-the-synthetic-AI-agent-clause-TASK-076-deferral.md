---
id: TASK-167
title: Remove the ~10 ms cost of the synthetic "AI agent$" clause (TASK-076 deferral)
status: To Do
assignee: []
created_date: '2026-10-02 09:27'
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
- [ ] #1 Either the engine applies the verified ids through a reusable id set or a per-document fast-field filter (with an index_version bump per the index-versioning skill if the schema changes), or the task is closed with a measured note that the cost no longer matters
- [ ] #2 The clause's per-search cost is re-measured at 80k before and after (docs/results/); no ID set, score or count changes (differential, golden)
<!-- AC:END -->
