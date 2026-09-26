---
id: TASK-019
title: RIS importer for the Trust-Evals corpus (scholarmend mended.ris)
status: To Do
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 01:35'
labels:
  - ingest
milestone: m-2
dependencies:
  - TASK-018
ordinal: 18000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
M2 bootstrap source (spec 01 §Sources); claim-only status rule.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Imports both mended.ris files; abstracts never Scholar snippets (… rejected)
- [ ] #2 status from claims only: venueid claim → its status; proceedings claim → accepted; none → unknown
- [ ] #3 provenance.source = ris; counts reported in the snapshot manifest
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Use the scholarmend PyPI package (pinned; v0.1.0 at 2026-09-25): scholarmend.parse.parse_ris for RIS, scholarmend.resolvers.openreview.parse_venueid for claims. Add it as a backend dependency when this task starts.
<!-- SECTION:NOTES:END -->
