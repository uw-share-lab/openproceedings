---
id: TASK-217
title: 'AIES 2026 proceedings: add OJS section rows once published'
status: To Do
assignee: []
created_date: '2026-10-10 03:47'
labels:
  - ingest
  - new-venues
milestone: m-4
dependencies: []
ordinal: 150000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
AIES 2026 (Malmö, 2026-10-12..14) was not on ojs.aaai.org on 2026-10-09. When AIES Vol. 9 appears, op ingest ojs --journal AIES stops on the unlisted volume; run scripts/ojs_section_census.py and add its rows to ingest/ojs_sections.toml.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 AIES 2026 rows verified and counts equal; snapshot diff additions only
<!-- AC:END -->
