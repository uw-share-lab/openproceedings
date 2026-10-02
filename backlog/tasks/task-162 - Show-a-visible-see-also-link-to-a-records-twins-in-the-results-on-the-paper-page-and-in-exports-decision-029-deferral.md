---
id: TASK-162
title: >-
  Show a visible see-also link to a record's twins in the results, on the paper
  page and in exports (decision-029 deferral)
status: In Progress
assignee: []
created_date: '2026-10-02 09:27'
updated_date: '2026-10-02 18:12'
labels:
  - frontend
  - export
  - dedup
  - deferred
dependencies:
  - TASK-159
references:
  - >-
    backlog/decisions/decision-029 -
    Link-ICLR-2017-workshop-copies-to-their-conference-twins-as-two-records-with-twin-claims-never-merged-the-RIS-importer-reads-scholarmend-0.1.5s-invitation-by-the-crawlers-twin-rule-TASK-159-TASK-157.md
priority: low
ordinal: 132000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: decision-029 (TASK-159), Consequences, Deferred. TASK-159 links an ICLR 2017 workshop-listing copy to its conference twin with a `twin` claim; the two stay separate records. Today the link shows only in the paper page's provenance table. A reviewer screening one copy should see that the other exists: a visible 'see also' in the results list and on the paper page, with each twin id clickable, and the twin ids carried in the exports. A `twin` claim can hold more than one id (two records have two-id values). Membership never changes: each record keeps matching on its own text (guarantee 5).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A result row and the paper page show a 'see also' line for a record with a `twin` claim, naming each twin id in the claim, each linking to that twin's paper page
- [ ] #2 Each export format carries the twin ids in a documented field (the specs and the ris-format/bibtex-format skills say which); a record without a twin exports byte-identically to today
- [ ] #3 Frontend tests (Vitest) cover a record with no twin, one twin and two twins; a contract test covers the API field, and `make openapi` output is committed
- [ ] #4 Search results, counts and ID sets are unchanged (differential and golden suites pass)
<!-- AC:END -->
