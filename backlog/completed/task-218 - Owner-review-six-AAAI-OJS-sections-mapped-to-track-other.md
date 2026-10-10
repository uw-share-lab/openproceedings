---
id: TASK-218
title: 'Owner review: five AAAI OJS sections mapped to track other'
status: Done
assignee: []
created_date: '2026-10-10 03:47'
updated_date: '2026-10-10 05:04'
labels:
  - ingest
  - new-venues
dependencies: []
ordinal: 151000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Sections the design's mapping doesn't name were mapped to other (excluded by default): NECTAR 2010-11, SHORT 2010, SPOT 2012, HOT 2015-17, SIS 2020 (five sections, 8 rows; docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md, 'For owner review'). ROBOT 2011/2013 ('Robotics Program') was a sixth: it moved to main in the milestone-A review gate, because AAAI-13's preface counts the AI and Robotics special track in its official 203 and the spec maps special tracks to main. AAAI 2023 Errata became front matter (ledger ruling). Moving a section is a one-line ojs_sections.toml edit and a snapshot-diff event.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Owner decision recorded per section and the table updated
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner decisions 2026-10-10: AAAI:SHORT (2010, 3) → main; NECTAR (2010-11), HOT (2015-17), SIS (2020) stay other (digests of work published elsewhere); SPOT (2012) stays other (content unconfirmed; revisit if the AAAI-12 programme shows otherwise). Applied in ojs_sections.toml (owner-decision comments), the research note and spec 01.
<!-- SECTION:NOTES:END -->
