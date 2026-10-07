---
id: TASK-204
title: NeurIPS 1987-2012 from the proceedings crawler
status: Done
assignee: []
created_date: '2026-10-07 03:15'
updated_date: '2026-10-07 05:44'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 147000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
proceedings.neurips.cc serves year pages for 1987 onward in the same shape as 2013+ (checked 2026-10-06), but the crawler refuses years before 2013 (decision-013). decision-047 lowers the floor to 1987.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 op ingest neurips accepts 1987-2012; a year before 1987 is refused
- [x] #2 Old listings classify as main by host and year (the token-less rule), with evidence; abstract placeholders such as 'Abstract Missing' are not stored as abstracts
- [x] #3 Tests use fixtures recorded from real pre-2013 year and abstract pages (scrubbed per decision-004)
- [x] #4 Official counts exist for NeurIPS 1987-2012 main and the live crawl matches them
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Lower neurips.FIRST_YEAR to 1987; record and scrub the 1987 year and abstract pages; crawl 1987-2012 live; add official counts from each year page's own count; fix what the real pages show (placeholders, PDF codes).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Live crawl 2026-10-06/07: 4,847 requests, 4,821 records, every listing's count matched. Focused review (track-classifier-auditor) found the 'Abstract Unavailable' placeholder (50+ pages) and (cid:N) extractor codes (1,676 records): both cleaned at ingest (common.clean_abstract, decision-047), counted (abstract_pdf_codes, abstract_short). Nit rejected: the 1987 fixture keeps the public proceedings editor's name, as the 2013-2025 NeurIPS fixtures do (scrub.py scrubs PMLR editors only).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
NeurIPS 1987-2012 are crawled from proceedings.neurips.cc (neurips.FIRST_YEAR 1987, decision-047). The live crawl (4,847 requests) gave 4,821 records, every year page's stated count matched, and 26 official-count rows (each page's own count) gate them: all within 0%. Old pages' 'Abstract Unavailable' placeholder is no abstract and (cid:N) PDF codes are repaired (1,676 records), both counted in each listing's report; 55 records lack an abstract. Tests: scrubbed 1987 year and abstract fixtures (test_neurips.py: the 1987 listing, placeholder, PDF codes, short abstracts, the 1986 refusal); make test, make lint and make tooling pass.
<!-- SECTION:FINAL_SUMMARY:END -->
