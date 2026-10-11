---
id: TASK-223
title: Make the IAAI and EAAI track expansions reachable without hovering
status: Done
assignee: []
created_date: '2026-10-10 05:50'
updated_date: '2026-10-10 18:38'
labels:
  - frontend
  - a11y
  - new-venues
milestone: m-3
dependencies: []
ordinal: 156000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the milestone A review gate (usability-auditor): the IAAI/EAAI badges show the acronym and expose the long form as their accessible name, but a sighted keyboard or touch user sees the expansion only through the pointer-only title. Add the expansions to the syntax-help glossary or the hit/paper details so every user can find them.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 IAAI and EAAI expansions visible without hover (glossary or details), with a test
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
IAAI and EAAI expansions are visible text: the syntax help's track row (from the generated golden's track_expansions) and the paper page's track badge ('IAAI (Innovative Applications of AI)'); hits keep the compact badge. Copy deck HS-3, PA-13, RH-11. Verified by Vitest (help, paper view, badge/golden agreement), the contract tests, make lint and make e2e on ports 8100/3100.
<!-- SECTION:FINAL_SUMMARY:END -->
