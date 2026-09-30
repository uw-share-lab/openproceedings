---
id: TASK-138
title: Exports name each abstract's source (decision-018)
status: To Do
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 02:40'
labels:
  - export
milestone: m-6
dependencies: []
ordinal: 121000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
decision-018 requires attribution wherever an abstract is shown or exported. TASK-134's review found no export names the abstract's source: RIS N1 and BibTeX note carry only the openproceedings line; RIS UR and BibTeX url give links but nothing says which source the abstract came from. Decide the mapping under the api-contract and export-format rules (an extra RIS N1 line or a CSV/JSONL column may be additive).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The export mapping for the abstract's source is decided and recorded (additive vs breaking per api-contract)
- [ ] #2 RIS, BibTeX, CSV and JSONL exports carry it, with round-trip tests against scholarmend's RIS parser and refaudit's BibTeX parser
<!-- AC:END -->
