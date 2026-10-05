---
id: TASK-188
title: Control characters inside abstracts split words in the index
status: To Do
assignee: []
created_date: '2026-10-05 08:39'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 132000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-180 cleaned titles only. Some abstracts hold U+0002 where a line-break hyphen was (modal, ity), so the word indexes as two tokens and an exact search for it misses the paper. Cleaning them changes stored bytes of existing records, so it needs its own decision on the rule and on the version bump.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The rule for control characters in abstracts is decided and recorded; affected records are counted on the current snapshot; the change, if made, bumps what index-versioning requires and the snapshot diff lists every changed record
<!-- AC:END -->
