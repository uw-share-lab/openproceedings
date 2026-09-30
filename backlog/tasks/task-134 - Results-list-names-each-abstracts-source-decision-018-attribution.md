---
id: TASK-134
title: Results list names each abstract's source (decision-018 attribution)
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 00:52'
updated_date: '2026-09-30 01:07'
labels:
  - frontend
milestone: m-6
dependencies: []
ordinal: 117000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-018 requires attribution and a source link on every record; PMLR's CC BY 4.0 needs a citation and a hyperlink to PMLR. TASK-063 found the paper page meets it (authors, links, per-field sources), but the results list (hit-item.tsx) shows the abstract with no authors and nothing naming where it came from.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each result shows authors and names the abstract's source with a link, without crowding the dense list (ui-design-system)
- [ ] #2 PMLR records carry the citation and PMLR hyperlink wherever their abstract is shown
- [ ] #3 Component and e2e tests pin it; exports' provenance noted if attribution must cover them
<!-- AC:END -->
