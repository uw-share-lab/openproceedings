---
id: TASK-139
title: Owner questions left by TASK-113 (v1 withdrawn twins)
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 02:40'
labels:
  - decision
milestone: m-4
dependencies: []
ordinal: 122000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-113 implemented the owner's rule (an accepted Blind note with a withdrawn twin becomes unknown) and left three questions for the owner: (1) should a Blind note with no decision plus a withdrawn twin become withdrawn (would clear ICLR 2018 main's 12 unknowns)? (2) 10 ICLR 2018 rejected Blind notes have withdrawn twins and stay rejected: correct? (3) should desk-rejected twins count too (none in the 2026-09-29 cache)? Also confirm the implementer's limits recorded in decisions 019/020 (withdrawn-only, same track, and the author-split guards).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The owner's answers are recorded in decision-020 (and 019 for the author guards)
- [ ] #2 Any rule change is implemented with tests and a real-data check; the coverage gate still passes
<!-- AC:END -->
