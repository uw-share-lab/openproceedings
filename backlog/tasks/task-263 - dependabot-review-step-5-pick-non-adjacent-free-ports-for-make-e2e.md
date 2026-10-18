---
id: TASK-263
title: 'dependabot-review step 5: pick non-adjacent free ports for make e2e'
status: In Progress
assignee: []
created_date: '2026-10-18 14:16'
updated_date: '2026-10-18 14:27'
labels:
  - tooling
  - dependabot
dependencies: []
priority: low
ordinal: 176000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the 2026-10-17/18 Dependabot batch: step 5's free-port recipe can give the web port as API port +1, but the e2e fixture server also serves API port +1 and +2 (TASK-182), so make e2e fails with EADDRINUSE before any test runs (hit twice; passed with non-adjacent ports).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The recipe picks ports at least 3 apart (or checks +1/+2 are free), and the skill says why
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Step 5's e2e row now points to a recipe below the table: a python3 snippet picks an API port a (random, multiple of 10 in 20000-60000) with a, a+1, a+2 and a+5 all free, and uses a+5 as the web port; the text says why (fixture server's tight/plain instances on +1/+2, TASK-182; EADDRINUSE twice in the 2026-10-17/18 batch). testing-standards skill's e2e-ports note says the same.
<!-- SECTION:NOTES:END -->
