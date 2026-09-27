---
id: TASK-046
title: 'Playwright e2e, accessibility and visual regression'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 20:20'
labels:
  - frontend
  - ops
milestone: m-3
dependencies:
  - TASK-044
  - TASK-043
  - TASK-045
ordinal: 45000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 05 §Testing; e2e workflow (e2e-tester, accessibility skills).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The spec 05 end-to-end flow passes against op serve on the fixture index
- [ ] #2 axe-core finds no WCAG 2.2 AA violations; keyboard-only flows pass
- [ ] #3 Visual regression for /search in both themes; e2e workflow added to CI
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Design (TASK-033, 2026-09-27): every wireframe state in docs/design/2026-09-27-*.md is an e2e or visual case (search W1-W14, builder B1-B2, export E1-E4, save S1-S3, record R1-R6, paper P1-P5, coverage C1); every 'Keyboard and screen reader' table is a keyboard-only Playwright flow; axe on each state in both themes at 320 px. Heuristic pre-pass: docs/design/2026-09-27-heuristic-prepass.md.
<!-- SECTION:NOTES:END -->
