---
id: TASK-186
title: 'Comparison: match a RIS record by DOI (Scopus and Web of Science exports)'
status: Done
assignee: []
created_date: '2026-10-05 08:39'
updated_date: '2026-10-06 00:20'
labels:
  - eval
  - ingest
milestone: m-3
dependencies: []
ordinal: 130000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The comparison matches by OpenReview forum id, proceedings id and title with venue and year. Exports from Scopus and Web of Science carry DOIs and often lack the URLs those rules read, so their records fall to title matching or not_in_index.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A DOI that names an indexed paper matches it under a rule stated in spec 07, never across venue or year, with fixtures from both export formats
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. RisRecord.dois from DO/DI and doi.org links (doi_key: prefix dropped, case-blind). 2. MatchIndex.dois from urls.doi (field and claims). 3. match(): DOI after the forum and proceedings ids, only in the venue/year the file states (where stated); elsewhere -> Match.doi_elsewhere, named in the gap row; two ids naming different records -> ambiguous. 4. MatchedBy gains doi (make openapi), frontend label, report text. 5. Synthetic Scopus and WoS fixtures; unit and /compare tests. 6. Spec 07/04 and protocol skill, with where the index holds DOIs.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Where the index holds DOIs (read-only count of snapshot 2026-10-05-10b5a205a63f behind index fd13d8d27535): 16,690 of 133,629 records, exactly the accepted NeurIPS 2022-2025 main, D&B and position papers (prefix 10.52202, NeurIPS pages' citation_doi). No ICLR, ICML, pre-2022 NeurIPS, workshop or rejected record has one, so DOI matching reaches only those; spec 07 says so. Rule choice: a venue string that is none of the three (WoS's 'ADVANCES IN ... 35 (NEURIPS 2022)') does not block a DOI, as it does not block a forum id; a stated year or recognised venue that differs always does. Fixtures: backend/tests/fixtures/ris/exports/{scopus,wos}.ris, hand-written in each vendor's field layout, synthetic titles and DOIs. Validation: test_scholar_compare.py 90 passed; targeted backend run (unit scholar + contract -k compare/scholar/openapi/schema/contract) 2070 passed, 1 skipped, 1 failed (the pre-existing date-dependent test_the_added_papers_come_as_the_exports_own_ris, also failing on clean HEAD); npm test --workspace frontend -- compare 41 passed (16 consecutive runs; 2 earlier runs had one intermittent failure while the machine was loaded).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
RIS records from Scopus and Web of Science exports now match an indexed paper by DOI (DO/DI or a doi.org link, case-blind), after the forum and proceedings ids and before the title rule, only in the venue and year the file states (where it states them); a DOI naming a record elsewhere is never a match and is named in the row; conflicting ids are ambiguous. matched_by gains 'doi' (openapi.json and schema.ts regenerated, frontend label). Spec 07 states the rule and that only accepted NeurIPS 2022-2025 records (16,690 of 133,629 on fd13d8d27535) carry a DOI. Tested on synthetic Scopus and WoS fixtures and end to end through POST /compare.
<!-- SECTION:FINAL_SUMMARY:END -->
