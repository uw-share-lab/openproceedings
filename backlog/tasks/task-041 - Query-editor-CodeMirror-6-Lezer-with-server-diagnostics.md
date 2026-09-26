---
id: TASK-041
title: Query editor (CodeMirror 6 + Lezer) with server diagnostics
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
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
