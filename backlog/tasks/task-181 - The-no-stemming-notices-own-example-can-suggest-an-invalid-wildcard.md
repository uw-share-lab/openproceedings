---
id: TASK-181
title: The no-stemming notice's own example can suggest an invalid wildcard
status: To Do
assignee: []
created_date: '2026-10-05 05:12'
labels:
  - query
  - ux
milestone: m-3
dependencies: []
references:
  - docs/specs/02-query-language.md
ordinal: 125000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
COMPAT_NO_STEMMING ends with an example built from the query's first term (e.g. ai$). For a query such as AI C++ or, the example is ai$, which the parser refuses as WILDCARD_STEM_TOO_SHORT. Found by TASK-175, which adds an action beside the notice that already knows which terms can take a $.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The notice's example is always a term that can take a $ as written (the same rule the word_forms list uses), or the example is omitted when no term qualifies
- [ ] #2 Help golden, copy deck and any fixture that quotes the message are regenerated through their generators; the message keeps its code and span
<!-- AC:END -->
