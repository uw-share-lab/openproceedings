---
id: TASK-043
title: Concept-group query builder
status: In Progress
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 21:41'
labels:
  - frontend
milestone: m-3
dependencies:
  - TASK-041
ordinal: 42000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 05 §Components 3 (query-builder-engineer).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Builder ↔ AST round-trip tests
- [x] #2 Read-only fallback when the AST doesn't fit the group shape
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Design (TASK-033, 2026-09-27): docs/design/2026-09-27-concept-group-builder.md + copy deck §3. Builder walks the server ast of the draft (never parses text); fits = top And of Or-of-leaves groups, one optional Not (Exclude row), top-level filters shown as read-only limits. Read-only notice names the first non-fitting construct with its kind and span (proximity, AND inside OR, a limit inside OR, NOT of a combination), focus moves to it. Builder edits are draft edits; Search dispatches builderEdit. Text->Builder->Text without an edit must leave the text byte-for-byte as typed; edited groups write canonical-equal q. Reorder by buttons (and Alt+Up/Down), no drag; focus after removal goes to the previous term/group. Test with main-7-most-updated in Scholar mode (source: limits keep their text).

Pre-pass fixes that land in TASK-043: pasted lists in one term offer 'Split into n terms' by default, else the chip says 'searched as one phrase' (M5); scope on each chip (S9); Search never disabled by the builder (S10); limits line says 'search first to edit them in Filters, or edit them in Text' (S8).

As built (t043): frontend/src/builder/ (model, read, terms, write, edits, concept-builder.tsx, query-tabs.tsx); the workspace mounts the tabs with a minimal, separate block in search-workspace.tsx (tab state, panels around the editor, builderEdit on Search from the Builder tab). Proof against the parser: builder-read-golden.json (backend-generated: 362 queries incl. Trust-Evals both modes, every fit-table row, 240 seeded random; server ast + an independent Python reading, which read.ts equals on all 349 parsed cases) and builder-write-golden.json (frontend-generated, UPDATE_BUILDER_GOLDEN=1: 295 unedited rewrites, 378 seeded random edits through the UI's own edit functions), checked by backend/tests/contract/test_frontend_builder_golden.py (unedited -> same canonical; edited -> each chip alone is one leaf and the query is exactly the chips' groups, no extra warning). Runtime check: the builder reads the server's ast of each query it wrote and alerts on any difference. Two blocker kinds added (NOT inside OR, a second NOT); new strings listed as copy deck BD-10 for ux-writer review. Not built: wildcard expansions under a group after Search (needs TASK-042's /search response), dimmed fitting groups under the read-only notice.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Built the Text/Builder tabs and the concept-group builder (frontend/src/builder/). The text stays canonical: the builder reads the server ast (groups, one Exclude row, limits kept as written; a query that doesn't fit is read-only, naming the first construct with its kind and span, with Edit in Text / Show it in the text) and rewrites the draft only after an edit: fully parenthesised, each term exactly one lexeme (checked with the generated lexer mirror, alone and in context). Pre-pass M5, S8, S9, S10 are in. Keyboard: arrow-key tabs, chips as buttons (Enter edits, Delete removes), Enter/Esc/Backspace in term boxes, Alt+Up/Down and buttons to reorder, focus after removal to the previous term/group, polite announcements. Verified: 362-case read golden (the TS reading equals the backend reference reading), 673-case write golden parsed by the backend (unedited gives the same canonical; edited gives exactly the chips), 21 UI tests with /parse answered from real server asts. uv run pytest (4584 passed, 2 skipped), npm test (2341), npm run build, make lint and make tooling are all green. Left In Progress because backlog task complete is refused in the worktree.
<!-- SECTION:FINAL_SUMMARY:END -->
