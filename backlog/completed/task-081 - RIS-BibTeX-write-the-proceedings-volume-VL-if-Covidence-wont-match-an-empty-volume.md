---
id: TASK-081
title: >-
  RIS/BibTeX: write the proceedings volume (VL) if Covidence won't match an
  empty volume
status: Done
assignee: []
created_date: '2026-09-27 07:52'
updated_date: '2026-09-27 17:50'
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
- [x] #1 Probe result read from docs/results/2026-09-27-covidence-check.md
- [x] #2 Decision recorded: VL written or not, and for which venue/track/status
- [x] #3 If written: spec 04 §Exports, ris-format/bibtex-format skills, export.py and tests updated
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Covidence hand check 2026-09-27 (docs/results/2026-09-27-covidence-check.md): probe 1 (identical but VL 36) and probe 3 (JOUR + VL 37) were matched as duplicates, so an empty volume doesn't block a Covidence match. Decision: the export does not write VL (nor BibTeX volume) for any venue/track/status. AC#3 is moot (nothing written).
<!-- SECTION:NOTES:END -->
