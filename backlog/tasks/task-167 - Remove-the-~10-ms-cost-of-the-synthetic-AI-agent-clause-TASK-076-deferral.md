---
id: TASK-167
title: Remove the ~10 ms cost of the synthetic "AI agent$" clause (TASK-076 deferral)
status: In Progress
assignee: []
created_date: '2026-10-02 09:27'
updated_date: '2026-10-02 18:43'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner decision 2026-10-02: do the schema change without breaking guarantee 4; after the end-to-end numbers below, kept (option a). SCHEMA_VERSION 3 indexes ord; a verified clause's ids are a u64 term set on it (TantivyEngine.id_set). index.SERVED_SCHEMAS maps each served schema (2 and 3) to its SchemaForm, and unservable accepts both, so a schema-2 index keeps the text-id term set and its pinned records still replay reproduced: 10/10 Trust-Evals records saved by the pre-change code (origin/dev 433399a9) on the real 05a0541717f6 replayed reproduced with a schema-3 build served, and test_records checks the same through the API. Identical ids and float scores on both schemas (test_served_schemas, test_verified_exclusion on both, the Trust-Evals strings in every sort before every timing). Measured (docs/results/2026-10-02-exclusions-and-verified-forms.md, alternated, load 30-155): the AI agent$ id set alone 11.3 -> 6.2 ms CPU; main-2-pop warm search CPU p50 29.4 vs 29.7 ms on the synthetic 80k and 26.4 vs 25.6 ms (about 3%) on the real corpus. The end-to-end gain is small because inside a search the id set is one MUST clause driven by the rarer clauses; TASK-076's ~10 ms was the clause resolved alone. A const-0 regex_phrase_query matched the same ids but cost 2-4x the id set. Schema 2 is retired (dropped from SERVED_SCHEMAS) once no record pins a schema-2 index: rebuild at schema 3, repoint current, op index retire each schema-2 version.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Schema 3 indexes ord, and a verified clause's ids are a u64 term set on it; schema 2 stays served (SERVED_SCHEMAS -> SchemaForm) so pinned records replay reproduced, which was checked on the real index with records saved by the pre-change code. Same ids and scores on both schemas. The measured end-to-end gain is small (0 on the synthetic 80k, about 3% on the real corpus); the clause alone went 11.3 -> 6.2 ms. Kept by owner decision. Results: docs/results/2026-10-02-exclusions-and-verified-forms.md.
<!-- SECTION:FINAL_SUMMARY:END -->
