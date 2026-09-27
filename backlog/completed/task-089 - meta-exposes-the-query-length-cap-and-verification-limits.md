---
id: TASK-089
title: /meta exposes the query-length cap and verification limits
status: Done
assignee:
  - '@api-engineer'
created_date: '2026-09-27 18:14'
updated_date: '2026-09-27 18:23'
labels:
  - api
milestone: m-3
dependencies: []
ordinal: 87000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From TASK-078's round-3 note: clients can't discover MAX_QUERY_LENGTH (2,000), max_verified_clauses (16) or max_verification_candidates (300,000), so the frontend hard-codes the cap. Add them to GET /meta additively (v1 frozen: required new fields per the contract rules) and derive the frontend's constant from it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 GET /meta returns the three limits; OpenAPI snapshot and schema.ts regenerated
- [x] #2 frontend MAX_QUERY_LENGTH comes from /meta (or the generated type) instead of a hand-kept constant
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Contract test: /meta limits (served config values, overridable) + frontend default-limits.json golden equals MAX_QUERY_LENGTH. 2. Limits model on MetaResponse, filled from parser + app.state.config; make openapi. 3. Frontend: QueryLimits type from schema.ts, DEFAULT_LIMITS from default-limits.json, reduce/whyBlocked take limits. 4. Spec 04/05, api-contract + nextjs-conventions skills.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
OpenAPI diff is additive: new schema Limits (3 required ints), new required MetaResponse.limits (always sent). Frontend has no /meta fetch yet, so reduce/whyBlocked take limits: QueryLimits (Pick of schema.ts Limits) defaulting to DEFAULT_LIMITS from frontend/src/lib/default-limits.json; backend test_meta_limits.py asserts that file equals /meta's served cap. TASK-041/042 pass the fetched limits.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
GET /meta now returns limits {max_query_length (parser MAX_QUERY_LENGTH), max_verified_clauses, max_verification_candidates (served ApiConfig)}; additive: new required Limits schema + required MetaResponse.limits; snapshot and schema.ts regenerated. Frontend: MAX_QUERY_LENGTH constant replaced by QueryLimits (from schema.ts Limits) and DEFAULT_LIMITS (frontend/src/lib/default-limits.json, used until /meta is fetched in TASK-041/042); reduce/whyBlocked take limits. backend/tests/contract/test_meta_limits.py pins served values, per-instance config, required-in-schema, and that default-limits.json equals /meta's cap. Spec 04/05, api-contract and nextjs-conventions skills updated. pytest 3662 passed/2 skipped; frontend 293 passed; make lint, make tooling green.
<!-- SECTION:FINAL_SUMMARY:END -->
