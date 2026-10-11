---
id: TASK-232
title: >-
  Find an official or open source of abstracts for the 3,648 AAAI 1980-2008
  records without one
status: Done
assignee: []
created_date: '2026-10-11 00:15'
updated_date: '2026-10-11 10:01'
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
- [x] #1 Each candidate source (aaai.org paper pages, the PDFs, others) is checked for abstracts, coverage by year and licence, and the findings are written to docs/research
- [x] #2 A recommendation is made: use one source, or leave the 3,648 as none, with the reason
- [x] #3 If a source is used, it is a new claim source with fixtures, official before OpenAlex in precedence, and the coverage report's Official abstract column counts it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Milestone C Task 16 (owner-approved 2026-10-10; decision-051). Built: the aaai_library claim source (record schema 9; after ojs, before crossref/facct_site/ris/openalex), ingest/aaai_library.toml + aaai_library_table.py (4,607 rows from scripts/aaai_library_census.py, 2 CDX requests on 2026-10-10: 4,709 AAAI 1980-2008 dblp records, 4,609 with a Library ee, 4,607 with a 200 capture, all the latest capture before 2023; 100 records have no ee, 2 pages no capture), sources/aaai_library.py (web.archive.org only, 3 s pacing, SHA-1 digest check at harvest and build, parser, post-dedup fill before OpenAlex's), op ingest aaai-library, Fetcher.get(exact_bytes=), the coverage report's AAAI line, fixtures (5 scrubbed captures), docs (spec 01/04/05/08, research note, copy deck, README, CLAUDE.md, skills). Design: a post-dedup fill like openalex, joined by dblp key (the replay of dblp_aaai is keyed by year and release and would fail on a half-harvested cache). Left open until the controller runs the full harvest (uv run op --data-dir <data> ingest aaai-library, about 4,607 requests, >= 3.8 h) and rebuilds the snapshot and index; AC #3 is ticked then, with the counts. Expect ~10% title_mismatch refusals from dblp OCR typos (2 of 15 samples): an owner ruling may be wanted. Follow-ups to file at the end of the branch: the 100 records with no ee and the 2 pages with no capture; op eval openalex could audit OpenAlex against these official AAAI abstracts.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Built the aaai_library claim source (decision-051): AAAI's own abstracts for AAAI 1980-2008 from Internet Archive captures of the old aaai.org paper pages, pinned by SHA-1 digest, aaai.org never fetched, filled after dedup and before OpenAlex. Real run (2026-10-11): 4,607 pages pinned, 0 missing, 1 unavailable (capture_redirect). Snapshot 2026-10-11-93c2937e2f29 (173,253 records): attached 4,536 of 4,709 candidates (126 title_near); refused title_mismatch 43, layout_unknown 23, undecodable 3, capture_redirect 1, no_abstract 1 (with 102 rows that had no page, the counts sum to 4,709); capture window 2016-05-05 to 2022-12-29. Against the snapshot before milestone C (2026-10-10-9efa49481112) 5,653 records changed, abstract only: abstract_kind none->official 4,536 (aaai_library) and none->openalex 1,117 (OpenAlex now fills 1,098 by DOI and 19 by title; AAAI 21, AIES 557, FAccT 539); none added, removed or rekeyed. Index b4f335e07e70 (schema 4): parity 0 differences over 214,499 terms and 344,268 phrases; abstract_kind:openalex gives 1,117 on both engines. op eval coverage --index b4f335e07e70 --check passes (81 of 82 gated cells plus the ICLR 2013 exception), and its Official abstract column counts the 4,536 (docs/results/2026-10-11-coverage.md). Docs restated: README, specs 01/03/07, design note, decisions 049 and 051, research note, coverage-sources, docs/README. The OpenAlex audit re-run on the final snapshot is TASK-235 (the offline re-run needs an uncached author lookup for the 19 title attaches).
<!-- SECTION:FINAL_SUMMARY:END -->
