---
id: TASK-224
title: >-
  Owner review: AIES 2018-2023 short entries (student abstracts, keynotes) sit
  in track main
status: To Do
assignee: []
created_date: '2026-10-10 10:37'
updated_date: '2026-10-10 11:41'
labels:
  - ingest
  - new-venues
milestone: m-4
dependencies: []
ordinal: 157000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Crossref carries no section data, so the 141 AIES 2018-2023 entries of two pages or fewer stay main (about 20 front-of-volume keynotes, 96 student abstracts, 25 short in-sequence papers; listed in docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md). From 2024 OJS labels student abstracts student_abstract, so the default search treats the two eras differently. Decide whether to add not_paper rows (keynotes) in ingest/acm_proceedings.toml, which are rows, and whether to give student abstracts the student_abstract track, which is a design change: the table has no track column (every Crossref record is main, decision-049), so it would gain one (a per-DOI track override) with a code and spec change. An official source for each row either way.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Owner decision recorded; table rows added if any, with evidence
<!-- AC:END -->
