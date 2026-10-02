---
id: TASK-160
title: Clip server-written values quoted in the remaining Coded messages
status: Done
assignee: []
created_date: '2026-10-02 00:59'
updated_date: '2026-10-02 06:09'
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
Source: a TASK-144 (PR #72) deferral (PR #72 body, Deferral). TASK-144 adds `frontend/src/lib/clip.ts`, the frontend twin of the backend's `diagnostics.clip`: a backtick and any Cc/Cf/Cs character are escaped, Python's `str.isspace()` set collapses to one space, and the value is cut to a width in code points. It applies `clip` to the values `search-state.ts` quotes, because a value holding a backtick shifts every later code span that `Coded` draws, and a control or bidi character reaches the page as it is. Other `Coded` messages still hold values the API returns (including /parse's slices of the user's own `q`) unclipped (`Coded` pairs every backtick in the whole message, so a value written outside a code span shifts the pairing as much as one inside it), which PR #72 left alone as not client text: `components/search/exclusion-banner.tsx` (each default clause), `components/search/exclusions.ts` (the filter values in an include button's description, bare and inside its clause, and `clauseText`) and `lib/replay-status.ts` (`replay.refused`, the index versions, and both query versions, written bare). They come from the API, so a hostile or corrupt record, index manifest or search record reaches them. The two clip implementations are also pinned only by a hand-copied table in `clip.test.ts`, which can drift from the backend. Depends on TASK-144 for `clip.ts`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Either `clip.test.ts`'s case table is generated from the backend `diagnostics.clip` (a backend contract test that fails when the committed table is stale, as the other frontend goldens are), or the reason not to is written in the error-diagnostics skill
- [x] #2 Every value the API returns (including /parse's slices of `q`) in a message `Coded` draws from `exclusion-banner.tsx`, `exclusions.ts` and `replay-status.ts` goes through `clip`, quoted or not: each default clause, the include description's bare value and its clause, `clauseText`, `replay.refused`, both index versions and both query versions; a literal the client code writes itself (a field name such as `track`) stays as it is
- [x] #3 Each call site has a test with hostile values (backtick, newline, NUL, ESC, U+202E) asserting the exact text and that the backticks still pair with no control or bidi character left, including a bare (unquoted) value; the banner's default-clause quoting gets a hostile-value test (`search-view.test.tsx` covers only ordinary clauses), as a component test or with the backtick join moved into `exclusions.ts` and unit-tested
- [x] #4 Ordinary values read exactly as before (the existing `exclusions.test.ts`, `replay-status.test.ts` and `search-view.test.tsx` banner tests pass unchanged), and the include label that strips backticks from its clause (`exclusions.ts`, `fails.replaceAll`) still reads correctly with a clipped value
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Generate clip.test.ts's cases from the backend clip (clip-golden.json + contract test); clip each API value in exclusions.ts and replay-status.ts; move the banner's backtick join into exclusions.ts (defaultsText); hostile-value tests per call site with a shared src/test/hostile.ts.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
clip-golden.json stores each input as code points: Vite's JSON loader rejects a lone surrogate escape. clauseText clips each value, not the whole clause, so the 47-code-point default track clause reads exactly as before. An include click still writes the raw value. The PRISMA disclosure stays plain text (not Coded), as before; its join is exclusions.ts::defaultsText. Review round 1 added clipping to the banner's other plain-text places (line 1, include label, accessible name, and the include announcement via includedText). Verified: vitest src/lib + src/components/search, test_frontend_clip_golden, eslint, tsc.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Every API value a Coded message quotes goes through clip, bare or in backticks: each include description's value and clause (exclusions.ts, clauseText per value) and the record replay lines (replay-status.ts: refused, both index versions, both query versions). The banner's plain-text strings clip the same values: the PRISMA disclosure's default clauses (clauseText, defaultsText), line 1's bucket names, each include label and accessible name, and the include announcement (includedText). Field names the client writes stay as written; ordinary text reads exactly as before. clip.test.ts reads clip-golden.json, generated from the backend diagnostics.clip by test_frontend_clip_golden.py (fails when stale). Hostile-value tests (backtick, newline, NUL, ESC, U+202E; shared src/test/hostile.ts) pin each call site's exact text and that backticks pair with nothing invisible left. Spec 05, the error-diagnostics skill and the copy deck updated.
<!-- SECTION:FINAL_SUMMARY:END -->
