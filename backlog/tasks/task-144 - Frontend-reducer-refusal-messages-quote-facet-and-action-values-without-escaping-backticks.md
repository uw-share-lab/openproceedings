---
id: TASK-144
title: >-
  Frontend reducer refusal messages quote facet and action values without
  escaping backticks
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 06:39'
labels:
  - frontend
  - bug
milestone: m-3
dependencies: []
references:
  - frontend/src/lib/search-state.ts
  - frontend/src/components/coded.tsx
ordinal: 121000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-141's review (PR #48, 2026-09-30). The URL↔state reducer (`frontend/src/lib/search-state.ts`) builds its `SearchStateError` refusal messages by wrapping values in backticks, e.g. `BAD_VALUE` at ~line 598 quotes `${v}`, where `v` comes from the clause values or the action (a URL, a facet click, a stale link). The messages are rendered by `Coded` (`frontend/src/components/coded.tsx`), which splits on backticks and pairs them, so a value that contains a backtick shifts every later code span, and a control character or newline goes through as is. This is the frontend twin of the backend bug TASK-141 fixed in `diagnostics.clip()` (backtick and Cc/Cf/Cs characters written as their escapes, whitespace runs collapsed).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every place the reducer quotes a value it did not write itself (facet values, action values, clause values, year text, page numbers) goes through one quoting helper that escapes backticks and control characters the way diagnostics.clip() does (same escapes, so the backend and frontend read alike)
- [ ] #2 A value containing a backtick, a newline, NUL, ESC or U+202E renders through `Coded` with the code spans still paired: Vitest cases for each refusal code that quotes a value, plus a property (fast-check or a table over hostile strings) asserting an even count of unescaped backticks in every refusal message
- [ ] #3 The error-diagnostics skill (or spec 05 §the reducer) says frontend refusal messages quote values through that helper
<!-- AC:END -->
