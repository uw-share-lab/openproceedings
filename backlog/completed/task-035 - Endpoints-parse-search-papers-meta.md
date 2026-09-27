---
id: TASK-035
title: 'Endpoints: /parse, /search, /papers, /meta'
status: Done
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 07:45'
labels:
  - api
milestone: m-3
dependencies:
  - TASK-034
ordinal: 34000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 04 §Endpoints and SearchResponse.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 SearchResponse has query (canonical, identification_query, warnings, translations, expansions), index/tokenizer/query versions, total, excluded, disjunctive facets, hits
- [x] #2 Parse errors are 422 with diagnostics; spans per spec 04
- [x] #3 Contract tests on the fixture index
- [x] #4 Contract test (decision-001): a facet removes only top-level conjuncts of its own field; a filter nested under OR stays applied
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built: openproceedings/search.py::run (op search now calls it too) + api/{models,search,papers,meta}.py; routers declared with prefix=/api/v1 and included directly (nested routers logged relative route templates: /healthz was logging at INFO; learning addendum). /parse answers 200 with errors (ParseResult as spec 02 defines it); /search 422s a query that doesn't parse. /papers reads the full record (provenance) from the index's snapshot via ingest.snapshot.RecordFile; missing/different snapshot = 500, so deploys must ship the snapshot. Tests: contract/test_search.py (AC1/AC4, op search equality, astral golden), test_parse_papers_meta.py (AC2, /parse, /papers, /meta, 503s, OpenAPI paths); probe search route replaced by the real /search in the skeleton tests. OpenAPI snapshot + TS codegen left to TASK-040. TASK-078 not done: its per-field clause summary is a new public shape spec 02/04 don't define (the non-toggleable representation, year values), and AC3 needs TASK-040's codegen. Spec gaps: /papers/{id} with the current query's highlights (spec 05 paper page) has no parameter in spec 04; hit has no status field in spec 04's example.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
GET /search, POST /parse, GET /papers/{id}, GET /meta over the one engine a request reads; /search runs the same search.run as op search (contract-tested equal ids, order, total). Every response carries the three versions; limit over 200 is 422 API_BAD_PARAM; parse errors 422 with code-point spans; disjunctive facets and excluded checked against ReferenceEngine; golden astral-plane title highlight test. Spec 04 as-built, CLAUDE.md, fastapi-conventions and api-contract skills updated.
<!-- SECTION:FINAL_SUMMARY:END -->
