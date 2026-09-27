---
id: TASK-046
title: 'Playwright e2e, accessibility and visual regression'
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-27 22:46'
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
From TASK-042/045: check the focus order (results header, banner and Limits line come before the sidebar in DOM order); Playwright + axe for /coverage and /help/syntax; consider widening SearchWorkspace's max-w-5xl now that the sidebar exists.
<!-- SECTION:NOTES:END -->
