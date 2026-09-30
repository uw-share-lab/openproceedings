---
id: TASK-140
title: WARN_MIXED_AND_OR message text drops a branch that failed to parse
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 02:40'
labels:
  - query
milestone: m-3
dependencies: []
ordinal: 123000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Since TASK-099, a mixed AND/OR level with a branch that failed to parse (e.g. 'a b OR () OR c') gets reading: null, so the editor offers no button, but the warning's message still quotes '(a b) OR c', silently dropping the failed branch in the prose.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The message matches the reading rule (quotes the level faithfully or omits the parenthesised reading when a branch failed)
- [ ] #2 Parser golden rows pin it
<!-- AC:END -->
