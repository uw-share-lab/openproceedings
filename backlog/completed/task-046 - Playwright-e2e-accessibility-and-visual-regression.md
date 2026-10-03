---
id: TASK-046
title: 'Playwright e2e, accessibility and visual regression'
status: Done
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-28 14:32'
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
- [x] #1 The spec 05 end-to-end flow passes against the deterministic fixture API and production frontend build
- [x] #2 axe-core finds no WCAG 2.2 AA violations in the selected state matrix; targeted keyboard flows pass
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
Design (TASK-033, 2026-09-27): use the wireframes and keyboard/screen-reader tables as the coverage inventory. TASK-046 automates the critical cross-stack journey, targeted keyboard interactions, and a representative axe matrix across success, error, disclosure, builder, dialog, paper, record, coverage and syntax states in both themes at 1280 and 320 px. Component tests retain exhaustive state and interaction coverage. Heuristic pre-pass: docs/design/2026-09-27-heuristic-prepass.md.

From TASK-042/045: check the focus order (results header, banner and Limits line come before the sidebar in DOM order); Playwright + axe for /coverage and /help/syntax; consider widening SearchWorkspace's max-w-5xl now that the sidebar exists.

Implemented with a synthetic 5,000-record fixture API and the production standalone frontend. The suite contains the full review flow, targeted keyboard paths, axe WCAG 2.2 AA scans, reflow checks and platform-specific visual snapshots. Final validation evidence is recorded in the closing commit and PR.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added deterministic Playwright E2E, representative WCAG 2.2 AA scanning, targeted keyboard coverage, mobile reflow, and light/dark visual regression coverage plus a fixed-Ubuntu-label CI workflow. The browser suite also drove target-size and contained-table overflow fixes on coverage and syntax pages.
<!-- SECTION:FINAL_SUMMARY:END -->
