---
id: TASK-204
title: NeurIPS 1987-2012 from the proceedings crawler
status: To Do
assignee: []
created_date: '2026-10-07 03:15'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 147000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
proceedings.neurips.cc serves year pages for 1987 onward in the same shape as 2013+ (checked 2026-10-06), but the crawler refuses years before 2013 (decision-013). decision-047 lowers the floor to 1987.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 op ingest neurips accepts 1987-2012; a year before 1987 is refused
- [ ] #2 Old listings classify as main by host and year (the token-less rule), with evidence; abstract placeholders such as 'Abstract Missing' are not stored as abstracts
- [ ] #3 Tests use fixtures recorded from real pre-2013 year and abstract pages (scrubbed per decision-004)
- [ ] #4 Official counts exist for NeurIPS 1987-2012 main and the live crawl matches them
<!-- AC:END -->
