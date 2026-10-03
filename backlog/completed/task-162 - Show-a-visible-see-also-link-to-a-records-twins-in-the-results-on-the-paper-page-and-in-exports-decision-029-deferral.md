---
id: TASK-162
title: >-
  Show a visible see-also link to a record's twins in the results, on the paper
  page and in exports (decision-029 deferral)
status: Done
assignee: []
created_date: '2026-10-02 09:27'
updated_date: '2026-10-03 02:13'
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
- [x] #1 A result row and the paper page show a 'see also' line for a record with a `twin` claim, naming each twin id in the claim, each linking to that twin's paper page
- [x] #2 Each export format carries the twin ids in a documented field (the specs and the ris-format/bibtex-format skills say which); a record without a twin exports byte-identically to today in RIS, BibTeX and JSONL, and CSV (fixed columns) gains one empty last column (additive under decision-021)
- [x] #3 Frontend tests (Vitest) cover a record with no twin, one twin and two twins; a contract test covers the API field, and `make openapi` output is committed
- [x] #4 Search results, counts and ID sets are unchanged (differential and golden suites pass)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Expose sorted twin ids in API hits/papers, results/paper links and four exports; preserve membership and no-twin compatibility; regenerate OpenAPI and exercise contract, frontend and browser tests.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Built: additive `twins` (sorted ids) on /search hits and /papers (RecordFile.twins, read from twin claims at load); openapi.json and schema.ts regenerated. Frontend TwinLinks (hit-item.tsx): 'See also (the same paper's other record(s)): <id>…' in each result after the abstract, and on the paper page before Abstract (copy RH-18, PA-10). Links carry q/mode (none from a direct link or a refused q). Exports: RIS N1 'See also: …' after the status sentence, before the abstract line (export.see_also); BibTeX openproceedings_twins; CSV last column twins; JSONL twins only on a record with one. An unverifiable snapshot names no twins. CSV is the one format not byte-identical for records without twins (one empty cell, decision-021 additive); AC #2 was reworded to say so. e2e: the fixture server twins the first two 'trust' hits; the a11y spec covers the line (axe in both themes at 1280/320, 24 px targets, 320 px reflow); darwin visual baselines regenerated (Linux baselines come from the CI run, as in TASK-134).

Final integration cdb68cdb6fc12bd0ae9c23bed1788e1fd1c78511 on merged dev9152ecb: make test PASS6386backend/2optional skips and3217frontend; make lint/tooling PASS; make e2e PASS19. Fresh focused index/dedup/twins/checker/takedown tests PASS289. Logs /tmp/twins-finalization-{test,lint,tooling,e2e,focused}.log. Independent integrated all-role review APPROVE /tmp/twins-integrated-all-role-review.md. Final metadata commit and its fresh fulltest/lint/tooling remain required before publication.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added visible clickable twin ids to results and paper pages and documented twin fields in RIS/BibTeX/CSV/JSONL. API contract regenerated; no-twin compatibility and unchanged membership verified by full6386backend/3217frontend suite plus19E2E tests.
<!-- SECTION:FINAL_SUMMARY:END -->
