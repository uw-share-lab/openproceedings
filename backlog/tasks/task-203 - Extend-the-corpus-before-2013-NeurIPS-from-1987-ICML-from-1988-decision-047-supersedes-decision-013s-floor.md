---
id: TASK-203
title: >-
  Extend the corpus before 2013: NeurIPS from 1987, ICML from 1988 (decision-047
  supersedes decision-013's floor)
status: To Do
assignee: []
created_date: '2026-10-07 03:15'
labels:
  - ingest
  - docs
milestone: m-4
dependencies: []
ordinal: 146000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The owner decided on 2026-10-06 to index the full history of NeurIPS and ICML. decision-013 kept every venue from 2013 (ICLR's first year) and said years before 2013 stay out until a spec change; this task records the new decision and makes the specs, coverage page, official counts, README and CLAUDE.md say what the corpus now holds, including that per-venue year coverage now differs (ICLR starts in 2013).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 decision-047 records the owner's decision, the sources per venue-year (NeurIPS proceedings 1987-2012; ICML from the pinned dblp snapshot release 1988-2012, abstracts from official ICML pages) and supersedes decision-013's pre-2013 exclusion
- [ ] #2 Spec 00 open question 3, spec 01 (Sources year ranges, crawl window, the dblp and ICML-site source rows, the abstract-source rule), spec 02's year coverage line and spec 04/07 wherever they state year ranges are updated
- [ ] #3 The coverage page and official counts cover the new venue-years, and say that ICLR has no pre-2013 years so cross-venue year counts differ before 2013
- [ ] #4 README and CLAUDE.md mention the new range and the new source
<!-- AC:END -->
