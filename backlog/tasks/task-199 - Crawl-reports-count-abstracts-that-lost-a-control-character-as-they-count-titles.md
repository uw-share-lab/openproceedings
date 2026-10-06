---
id: TASK-199
title: >-
  Crawl reports count abstracts that lost a control character, as they count
  titles
status: To Do
assignee: []
created_date: '2026-10-06 01:27'
labels:
  - ingest
  - observability
milestone: m-4
dependencies: []
ordinal: 142000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-188 (decision-044) replaces each control character in an abstract by one space at import and records the count only in the abstract claim's evidence. OpenReview crawl reports count titles that lost one (title_control_characters) but have no matching counter for abstracts, so a crawl's attention summary can't show it. Raised by the TASK-188 implementer on 2026-10-06.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every importer that supplies an abstract reports how many abstracts had a control character replaced, beside the title counter, with tests and spec 01 as built
<!-- AC:END -->
