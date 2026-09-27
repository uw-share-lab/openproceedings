---
id: TASK-087
title: >-
  Paper page highlights: a q param on GET /papers/{id}, or client-side from
  /search
status: In Progress
assignee: []
created_date: '2026-09-27 11:33'
updated_date: '2026-09-27 18:02'
labels:
  - api
  - frontend
milestone: m-3
dependencies:
  - TASK-035
ordinal: 85000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found at the M3a docs gate. Spec 05 §Pages has /paper/[id] show the abstract with the current query's highlights, but GET /papers/{id} (spec 04) takes no q and returns no highlights, and the client may not re-match (spec 05 §Components 6; nextjs-conventions). Either add an optional q (+ mode) to GET /papers/{id} that returns highlights computed by engine/highlight.py exactly as /search does (additive under v1: a new optional parameter, a new always-sent field), or carry the hit's highlights from the /search response the reader came from (then a direct link to /paper/[id] shows none). Decide, update spec 04/05, make openapi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Spec 04 and 05 say how /paper/[id] gets its highlights, and a direct link without q is handled
- [x] #2 If the API route changes: contract test for highlights equal to /search's for the same q, record and index; openapi snapshot and schema.ts regenerated
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Server side: optional q (+mode) on GET /papers/{id}; admit q through deps.searchable + check_candidates (same as /search); search.highlight builds /search's Highlighter over the display record (Highlighter.match returns None on no match); additive matched + highlights fields; contract tests incl. equality with /search over Trust-Evals strings and the astral golden; spec 04/05 + api-contract skill; make openapi.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decision (spec 04 §Implementation notes, 'Paper-page highlights'): server-side q, not client carry-over (a direct/shared/reloaded link keeps its highlights; q stays the only URL state). PaperResponse gains matched (bool|null) and highlights (Highlights|null), both null without q; a q that doesn't match the paper (default filters included) is matched:false with empty lists, not an error. q admitted exactly as /search: strict params (mode=scholar without q is 422), length cap, parse 422 with diagnostics, over-cap wildcard, verified-clause cap and charge, candidate ceiling; admitted before the 404 lookup. 503 API_BUSY declared (as every query route) but never sent today: the paper's own text is evaluated by the highlighter, no collection or position verification. Tests: backend/tests/contract/test_paper_highlights.py (35), equality hit-by-hit with /search over the 10 Trust-Evals strings (357 hits) and 6 native queries; QUERY_ROUTES in test_contract_v1 now includes /papers/{id}. make openapi regenerated openapi.json and schema.ts (additive diff only).

All ACs met and final summary written; 'backlog task complete' was refused by the agent sandbox, so status is left In Progress to keep check_backlog green: run 'backlog task edit TASK-087 -s Done' then 'backlog task complete TASK-087'.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
GET /papers/{id} takes an optional q (+mode) and always sends matched + highlights (null without q): additive under v1. Spans come from search.highlight, the same Highlighter, display record and expansions /search uses; a non-matching q is matched:false with empty lists. q admitted exactly as /search (strict params, length cap, parse, wildcard cap, verified-clause cap/charge, candidate ceiling); never logged. Spec 04/05 and api-contract skill updated; make openapi. Verified: test_paper_highlights.py (35 tests: equality with /search over 357 Trust-Evals hits + native queries, astral golden, refusals, charge, log), full uv run pytest 3539 passed, make lint, make tooling.
<!-- SECTION:FINAL_SUMMARY:END -->
