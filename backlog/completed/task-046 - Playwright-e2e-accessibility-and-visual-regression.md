---
id: TASK-046
title: 'Playwright e2e, accessibility and visual regression'
status: Done
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-28 04:20'
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
- [x] #1 The spec 05 end-to-end flow passes against op serve on the fixture index
- [x] #2 axe-core finds no WCAG 2.2 AA violations; keyboard-only flows pass
- [x] #3 Visual regression for /search in both themes; e2e workflow added to CI
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Build a deterministic synthetic fixture index and run its API plus the standalone frontend under Playwright.
2. Exercise the spec 05 search, query-tree, workshop inclusion, RIS export, save and replay flow, including keyboard focus behavior.
3. Run axe and mobile reflow checks across core pages in both themes, capture /search visual baselines, and add the E2E CI workflow.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Design (TASK-033, 2026-09-27): every wireframe state in docs/design/2026-09-27-*.md is an e2e or visual case (search W1-W14, builder B1-B2, export E1-E4, save S1-S3, record R1-R6, paper P1-P5, coverage C1); every 'Keyboard and screen reader' table is a keyboard-only Playwright flow; axe on each state in both themes at 320 px. Heuristic pre-pass: docs/design/2026-09-27-heuristic-prepass.md.

From TASK-042/045: check the focus order (results header, banner and Limits line come before the sidebar in DOM order); Playwright + axe for /coverage and /help/syntax; consider widening SearchWorkspace's max-w-5xl now that the sidebar exists.

Implemented with a synthetic 5,000-record fixture and the production standalone frontend. Validation: Playwright 9 passed (full flow, keyboard, axe WCAG 2.2 AA in light/dark at 1280/320, reflow, visual snapshots); Vitest 2,556 passed; pytest 5,074 passed with 2 opt-in skips; lint and tooling gates passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added deterministic Playwright E2E, WCAG 2.2 AA, keyboard, mobile reflow, and light/dark visual regression coverage plus a pinned CI workflow. The browser suite also drove target-size and contained-table overflow fixes on coverage and syntax pages.
<!-- SECTION:FINAL_SUMMARY:END -->
