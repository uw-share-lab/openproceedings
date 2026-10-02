---
id: TASK-160
title: Clip server-written values quoted in the remaining Coded messages
status: To Do
assignee: []
created_date: '2026-10-02 00:59'
updated_date: '2026-10-02 00:59'
labels:
  - frontend
  - bug
milestone: m-3
dependencies:
  - TASK-144
references:
  - frontend/src/components/search/exclusion-banner.tsx
  - frontend/src/components/search/exclusions.ts
  - frontend/src/lib/replay-status.ts
  - backend/src/openproceedings/diagnostics.py
  - .claude/skills/error-diagnostics/SKILL.md
priority: medium
ordinal: 135000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: a TASK-144 (PR #72) deferral (PR #72 body, Deferral). TASK-144 adds `frontend/src/lib/clip.ts`, the frontend twin of the backend's `diagnostics.clip`: a backtick and any Cc/Cf/Cs character are escaped, Python's `str.isspace()` set collapses to one space, and the value is cut to a width in code points. It applies `clip` to the values `search-state.ts` quotes, because a value holding a backtick shifts every later code span that `Coded` draws, and a control or bidi character reaches the page as it is. Other `Coded` messages still put server-written values between backticks unclipped, which PR #72 left alone as not client text: `components/search/exclusion-banner.tsx` (each default clause), `components/search/exclusions.ts` (the filter values and clause text in an include button's description, `clauseText`) and `lib/replay-status.ts` (`replay.refused` and the index versions). They come from the API, so a hostile or corrupt record, index manifest or search record reaches them. The two clip implementations are also pinned only by a hand-copied table in `clip.test.ts`, which can drift from the backend. Depends on TASK-144 for `clip.ts`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every server-written value that `exclusion-banner.tsx`, `exclusions.ts` and `replay-status.ts` quote between backticks goes through `clip` (default clauses, filter values and clause text, `replay.refused`, both index versions); a value written by the client stays as it is
- [ ] #2 Each call site has a test with hostile values (backtick, newline, NUL, ESC, U+202E) asserting the exact text, and that the backticks still pair with no control or bidi character left
- [ ] #3 Ordinary values read exactly as before (the existing tests for the three files pass unchanged)
- [ ] #4 Either `clip.test.ts`'s case table is generated from the backend `diagnostics.clip` (a backend contract test that fails when the committed table is stale, as the other frontend goldens are), or the reason not to is written in the error-diagnostics skill
<!-- AC:END -->
