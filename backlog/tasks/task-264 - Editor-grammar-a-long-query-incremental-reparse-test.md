---
id: TASK-264
title: 'Editor grammar: a long-query incremental-reparse test'
status: In Progress
assignee: []
created_date: '2026-10-18 14:16'
updated_date: '2026-10-18 14:27'
labels:
  - frontend
  - test
dependencies: []
priority: low
ordinal: 177000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Optional, from the #165 review (2026-10-18): @lezer/lr 1.4.11 changed fragment reuse; a reviewer's 16k-edit fuzz found no differences, but frontend/src/editor/lang/grammar.test.ts has no long-query incremental-reparse case.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 grammar.test.ts compares incremental and full parses over a long query under random edits
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
grammar.test.ts: 'holds over a long query under 200 seeded random edits': every golden input joined (~12k chars), mulberry32(264) edits that replace 0-3 characters with operator/field/phrase/math/astral snippets (never splitting a surrogate pair), each incremental parse chained on the last one's fragments as the editor does, compared with a full parse at every step (cheap JSON compare, toEqual only to show a difference, with the step in the message). It also asserts more than 150 of 200 steps kept an old subtree (199 do), so the incremental path really runs. Checked that a wrong-fragment mutant (change not mapped) fails at step 0. ~5s locally; 60s timeout for loaded machines.
<!-- SECTION:NOTES:END -->
