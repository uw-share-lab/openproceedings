---
id: TASK-182
title: >-
  End-to-end and accessibility tests for the word-forms action, builder group
  counts and the RIS comparison
status: To Do
assignee: []
created_date: '2026-10-05 05:12'
labels:
  - frontend
  - e2e
  - a11y
milestone: m-3
dependencies:
  - TASK-175
  - TASK-176
  - TASK-177
references:
  - docs/specs/05-frontend.md
ordinal: 126000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-175, TASK-176 and TASK-177 each shipped with unit and contract tests only: Playwright binds ports 3000 and 8000, which the owner's running instance held while they were built. Three new UI surfaces would otherwise release without browser, axe or visual coverage.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 frontend/e2e covers: Scholar string, Add $ (all and chosen terms), Search, URL carries the $, expansions shown, Back restores the typed query
- [ ] #2 frontend/e2e covers: builder group counts and without-counts after a search, hidden when the draft differs, the too-many and too-costly notes, the live announcement
- [ ] #3 frontend/e2e covers: the RIS comparison from upload to the kept, dropped, added and not-in-index lists and their exports, the disabled state, and an over-cap file
- [ ] #4 axe passes WCAG 2.2 AA on each new state and the 320 px reflow check passes; visual snapshots are added through the suite's own update command
- [ ] #5 make e2e passes locally and the run's counts are recorded in the task
<!-- AC:END -->
