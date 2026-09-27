---
id: TASK-041
title: Query editor (CodeMirror 6 + Lezer) with server diagnostics
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 20:27'
labels:
  - frontend
milestone: m-3
dependencies:
  - TASK-039
  - TASK-040
  - TASK-033
ordinal: 40000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 05 §Components 1–2 (codemirror-lezer skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Highlighting mirrors spec 02; server /parse is authoritative; 250 ms debounce
- [ ] #2 Squiggles from server spans converted once in src/api/spans.ts
- [ ] #3 'How we read your query' AST tree with defaults shown
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Design (TASK-033, 2026-09-27): build from docs/design/2026-09-27-search-workspace.md §W1-W4, W6, W7, W11 + §Interaction spec (editor, diagnostics summary/row, expansions, translations row, 'How we read your query' tree, URL notice box W2, Revert edits) and copy deck §1-2. Key rules: Enter submits / Shift-Enter newline / Tab leaves the editor; F8 next diagnostic (lintKeymap), bind previousDiagnostic to Shift-F8; the summary is a polite live region updated after the debounced /parse and after each search; squiggles differ by line style + gutter glyph (never colour alone); every diagnostic has Help ▸ -> /help/syntax#<code lower case> (#slow-clauses for the two API_ codes). Two parse queries: [parse, draft, mode] for squiggles and [parse, q, mode] for the searched q (sidebar/banner). WILDCARD_TOO_MANY_EXPANSIONS, API_TOO_MANY_VERIFIED_CLAUSES and API_QUERY_TOO_COSTLY only come from /search 422s: draw them as squiggles on the submitted q, with copy ED-10. 413 on /parse -> ED-11. The tree opens by default on zero results and when WARN_MIXED_AND_OR is present ('Show how it was read' opens it and moves focus). Follow-up for ux-writer (not a TASK-041 blocker): seven proposed registry wording changes with golden updates, copy deck §Before/after (PARSE_UNBALANCED_PAREN, PARSE_ALL_NEGATIVE 'excluded' glossary clash, PARSE_TOO_DEEP, PARSE_STRAY_COLON, PARSE_TOO_LONG, FIELD_FILTER_SYNTAX, WARN_CJK_RUN); needs a Backlog task from the main session.

Pre-pass fixes that land in TASK-041 (docs/design/2026-09-27-heuristic-prepass.md): the draft is (text, mode) - a Syntax change alone makes it dirty; while dirty the row and tree show the draft's /parse labelled 'Draft - not searched' and a 'Searched query: n warnings' line stays (M6, M7); repeated codes collapse to 'n x' (M8); FIELD_COMPAT_ONLY offers 'Read as Google Scholar syntax' (sets the select only, M8); WARN_MIXED_AND_OR offers 'Load with parentheses' (draft only, S7); the home page offers main-7-most-updated verbatim in Scholar mode (S11).
<!-- SECTION:NOTES:END -->
