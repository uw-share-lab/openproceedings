---
id: TASK-181
title: The no-stemming notice's own example can suggest an invalid wildcard
status: In Progress
assignee: []
created_date: '2026-10-05 05:12'
updated_date: '2026-10-05 05:25'
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
- [x] #1 The notice's example is always a term that can take a $ as written (the same rule the word_forms list uses), or the example is omitted when no term qualifies
- [x] #2 Help golden, copy deck and any fixture that quotes the message are regenerated through their generators; the message keeps its code and span
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built on task-181-notice-example. The rule for where a $ fits moved to query/exact.py::dollar_places, below parser.py and wordforms.py, so the notice's example and word_forms share one implementation and parse does not recurse. The example is the first qualifying term (a phrase quoted whole); none when no term qualifies or the term can't be quoted whole in 40 characters. Code and span unchanged. Regenerated: syntax-golden.json (one added AI ML example), word-forms-golden.json, record-fixture.json; openapi unchanged.
<!-- SECTION:NOTES:END -->
