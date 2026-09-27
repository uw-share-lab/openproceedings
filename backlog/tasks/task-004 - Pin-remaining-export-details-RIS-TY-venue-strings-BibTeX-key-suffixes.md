---
id: TASK-004
title: 'Pin remaining export details (RIS TY, venue strings, BibTeX key suffixes)'
status: In Progress
assignee: []
created_date: '2026-09-25 22:06'
updated_date: '2026-09-27 07:52'
labels:
  - api
milestone: m-3
dependencies: []
references:
  - .claude/skills/ris-format/SKILL.md
ordinal: 4000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Left open by spec 04; ris-format and bibtex-format skills flag them.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 RIS TY value chosen (CPAPER vs JOUR) and checked by importing into Covidence
- [x] #2 Canonical T2 venue strings for NeurIPS, ICLR and ICML by year
- [x] #3 BibTeX collision rule: whether the first colliding key stays bare or gets 'a'
- [x] #4 Spec 04 updated
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. T2 table: conference name + that year's acronym, cited, every year each venue was held; tests. 2. BibTeX collision rule: decision record + tests pinning bare-first and superset behaviour. 3. TY: CPAPER reasoning; Covidence fixture + checklist in docs/results (human import pending). 4. Spec 04 §Exports + ris-format/bibtex-format skills.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC#1 PENDING the human Covidence import: TY is CPAPER (reasoning in spec 04 §Exports). Import docs/results/2026-09-27-covidence-fixture.ris (and the dedup probe) into a THROWAWAY Covidence review following docs/results/2026-09-27-covidence-check.md, fill in its results, then tick AC#1 and complete the task. backend/tests/unit/test_covidence_fixture.py pins the fixture byte for byte to the writer.
AC#2: T2/booktitle = '<conference name> (<acronym that year> <year>)' via export.CONFERENCES / venue_name(): NeurIPS NIPS 1987-2017, NeurIPS 2018+; ICLR 2013+; ICML 1988+; earlier years refused. Conference name rather than proceedings title because workshop/rejected/ICLR papers are in no proceedings. Sources cited in spec 04.
AC#3: decision-007 (accepted): first use bare, then a, b in id order, per file (as task-030 built it; matches Better BibTeX and JabRef). Superset trade-off pinned by test.
AC#4: spec 04 §Exports, ris-format and bibtex-format skills updated.
Follow-up: TASK-081 (write VL if the Covidence probe shows an empty volume blocks dedup).
<!-- SECTION:NOTES:END -->
