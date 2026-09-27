---
id: TASK-081
title: >-
  RIS/BibTeX: write the proceedings volume (VL) if Covidence won't match an
  empty volume
status: To Do
assignee: []
created_date: '2026-09-27 07:52'
labels:
  - api
dependencies:
  - TASK-004
priority: low
ordinal: 79000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Covidence matches duplicates on title, year, volume and authors. Our RIS has no VL, while other databases' copies of NeurIPS/ICML papers often carry one (NeurIPS: Advances volume = year - 1987; ICML: the PMLR volume). docs/results/2026-09-27-covidence-dedup-probe.ris (task-004 checklist, step 5) shows whether an empty volume blocks a match. If it does, decide VL (and BibTeX volume) for accepted papers in proceedings tracks only; ICLR, workshop and rejected papers have none.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Probe result read from docs/results/2026-09-27-covidence-check.md
- [ ] #2 Decision recorded: VL written or not, and for which venue/track/status
- [ ] #3 If written: spec 04 §Exports, ris-format/bibtex-format skills, export.py and tests updated
<!-- AC:END -->
