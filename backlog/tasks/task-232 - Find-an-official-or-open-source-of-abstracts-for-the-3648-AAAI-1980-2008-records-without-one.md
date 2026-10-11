---
id: TASK-232
title: >-
  Find an official or open source of abstracts for the 3,648 AAAI 1980-2008
  records without one
status: To Do
assignee: []
created_date: '2026-10-11 00:15'
labels:
  - ingest
  - new-venues
dependencies: []
ordinal: 161000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
After the OpenAlex fill, 3,648 of the 4,709 AAAI 1980-2008 records still have no abstract (abstract_kind none), so a review searching those years matches only on titles. OpenAlex's AAAI source holds about 23% of those years' papers (it files 20 to 50% of each year's, and fewer in later years). aaai.org's paper pages are the first place to look, and the PDFs themselves another; the research note records that aaai.org sets a Crawl-delay of 43200 on its crawler paths, which any approach must respect. Every candidate source needs its licence checked before anything is served, on the publisher-abstract posture of decision-018 and the takedown process.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each candidate source (aaai.org paper pages, the PDFs, others) is checked for abstracts, coverage by year and licence, and the findings are written to docs/research
- [ ] #2 A recommendation is made: use one source, or leave the 3,648 as none, with the reason
- [ ] #3 If a source is used, it is a new claim source with fixtures, official before OpenAlex in precedence, and the coverage report's Official abstract column counts it
<!-- AC:END -->
