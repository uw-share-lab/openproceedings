---
id: TASK-111
title: >-
  Builder: wildcard expansions under each group, and the fitting groups dimmed
  when read-only
status: Done
assignee: []
created_date: '2026-09-27 22:46'
updated_date: '2026-09-30 05:39'
labels:
  - frontend
milestone: m-3
dependencies: []
ordinal: 108000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-043 proposals: after Search, show each group's wildcard expansions from the /search response; when the builder is read-only, show the groups that did fit, dimmed, under the notice (design B2).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Expansions shown per group from /search,Read-only view shows fitting groups dimmed and not editable,Keyboard and screen-reader tests
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Frontend only. read.ts: readParts walks each top-level part on its own; readAst reports the first blocker, readFitting returns the fitting shape. expansions.ts: termWildcards maps each term span to the <stem><op> keys of the server ast's wildcards inside it. SearchView passes the last good /search expansions through SearchWorkspace to ConceptBuilder; GroupExpansions renders ExpansionLine per key; carryKeys keeps unchanged terms' keys while /parse of an edit is in flight. ReadOnly renders FittingParts (region, dimmed, no controls) under the BD-7 notice.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Copy BD-11 reviewed by ux-writer (adopted: heading 'Parts that fit the builder', line 'Anything that doesn't fit is left out. Nothing here can be edited.', 'Group <n>' without 'of <m>', AND NOT only after a group). Mutation checks: dropping carryKeys fails the held-/parse test; dropping the SearchView prop fails the search-view integration test. Validation: npm test --workspace frontend (37 files, 3023 passed), make lint (exit 0), make tooling (exit 0).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
After a search, each builder group and the Exclude row list their own wildcards' expansions from the /search answer (keys from the server's ast of the draft, worded as the Expansions row; kept for unchanged terms while an edit is being read). A read-only (too complex) query shows its fitting groups, first Exclude row and limits under the notice in a 'Parts that fit the builder' region, dimmed and with no controls. Verified by tests: readFitting equals readAst on every fitting golden query and keeps the fitting parts of blocked ones; termWildcards on golden asts; UI tests for per-group lines and screen-reader text, none before a search, keyboard reach of +N more, the read-only region's names, no tabbable controls, the panel's Tab order, AND NOT placement; search-view integration. npm test --workspace frontend 3023 passed; make lint and make tooling green. Docs: design as-built (TASK-111), copy deck BD-11, CLAUDE.md.
<!-- SECTION:FINAL_SUMMARY:END -->
