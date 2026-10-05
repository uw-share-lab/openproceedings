---
id: TASK-190
title: Decide what ICML 2026 regular means for presentation
status: To Do
assignee: []
created_date: '2026-10-05 08:39'
labels:
  - ingest
  - decision
milestone: m-4
dependencies: []
ordinal: 134000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
ICML 2026's accepted notes carry the venue strings ICML 2026 regular (5,805) and ICML 2026 Position Paper Track regular (175). Nothing recorded says a regular paper was a poster, so TASK-178 left them unmapped and every ICML 2026 crawl warns with presentation_unmapped 5,980, which would hide a genuinely new string. The owner's interim choice (2026-10-05) is to leave them blank.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The mapping (poster, a stated-none value, or blank) is decided with evidence from ICML, recorded, and the standing warning either goes away or is replaced by a check that names new strings
<!-- AC:END -->
