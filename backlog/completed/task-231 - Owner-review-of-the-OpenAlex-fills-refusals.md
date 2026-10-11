---
id: TASK-231
title: Owner review of the OpenAlex fill's refusals
status: Done
assignee: []
created_date: '2026-10-11 00:15'
updated_date: '2026-10-11 01:46'
labels:
  - ingest
  - new-venues
dependencies: []
ordinal: 160000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The real fill (snapshot 2026-10-10-22a339940466, extract 7fea58b983252594b9ad3fb4788022f81b64adf579ce9cee129abf91a9c5c49c) refused 3,650 of its 5,808 candidates; the rules refuse rather than guess, and a person should look at the few that might be wrong. Counts from the manifest, sources.openalex.fills: doi_duplicate 2 (the two DOIs behind AIES 2019 and FAccT 2021, where several works carry differing texts); title_ambiguous 21 (several candidates on one side of the exact title-key join); inverted_unreadable 101 and inverted_gap 50 (the index could not be rebuilt faithfully); no_abstract 119; title_unmatched 3,357 (no OpenAlex work with that title key, not a defect). Of the works whose index was inverted_unreadable, 117 AAAI works are refused only because a key holds a line break (word with CR or LF), per docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md §OpenAlex (the 117 counts works in the listings, the 101 counts records, so they differ). Whether such a key should be split or stripped, rather than refused, is the owner's call.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The 2 doi_duplicate DOIs are listed with each work's text, and the owner picks one, or confirms the refusal
- [x] #2 The 21 title_ambiguous cases are listed and each is attached by hand-checked evidence or confirmed refused
- [x] #3 The 117 AAAI works refused for line breaks in their index keys are listed, and the owner decides to split or strip such keys, or to keep refusing
- [x] #4 Any change to the rules is made in sources/openalex.py with its tests and spec 01, and the outcome is recorded in the OpenAlex row of spec 01
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Owner rulings 2026-10-10: (1) collapse whitespace inside an inverted-index key to one space at its one position; still refuse blank keys, gaps, conflicts. (2) A cited [[duplicate_choice]] row in openalex_sources.toml pins W2796639635 for AIES 2019's 10.1145/3306618.3314250; the fill attaches it (attached_doi + duplicate_chosen) and stops (duplicate_choice_unmatched) if the extract no longer answers the DOI with that work among two or more. (3) Everything else stays refused. TDD in test_openalex_parse/fill/table; docs in spec 01, the research note §OpenAlex (TASK-231) and the plan.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Evidence: a read-only replay of snapshot 2026-10-10-22a339940466 / extract 7fea58b98325 reproduced the manifest's refusals exactly (doi_duplicate 2, title_ambiguous 21, inverted_unreadable 101, inverted_gap 50, no_abstract 119, title_unmatched 3,357). The 117 line-break works (101 records) are one token per key: in every otherwise-dense index the multi-word key holds one position with the next word at p+1.
Rule 1 (rebuild): each whitespace run in a key becomes one space and edge whitespace is dropped (5 keys start with CRLF, one of them in BowlingWG06, which the predicted 89 needs); an empty or whitespace-only key stays inverted_unreadable; gaps and conflicts unchanged. Replaces Task 7's 'a key with whitespace inside is unreadable'.
Rule 2: openalex_table.DuplicateChoice / Table.duplicate_choices loaded from [[duplicate_choice]] (doi, work, reason, verified, source; bare lower-case DOI, W id, no DOI twice). fill's _check_choices raises CrawlError duplicate_choice_unmatched (a SnapshotError at build) when a queried DOI's works do not include the chosen one among two or more; a DOI the extract never asked leaves the row inert. The chosen work alone is attached; if its own abstract is unusable the record is refused with that reason, never another work. FillReport.duplicate_chosen in the manifest.
Kept refused per ruling: FAccT 2021 10.1145/3442188.3445881, all 21 title_ambiguous (Shvaytser 1990 included), inverted_gap, no_abstract, title_unmatched.
Predicted (offline fill of the extract over the snapshot's records with OpenAlex claims removed; snapshot NOT rebuilt): attached_doi 1,098 (duplicate_chosen 1), attached_title 1,150 (+89), refused inverted_unreadable 2, inverted_gap 60 (+10), doi_duplicate 1, title_ambiguous 21, no_abstract 119, title_unmatched 3,357.
Validation: openalex tests 163 passed; full backend suite 8,885 passed, 3 skipped; make lint clean.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Owner rulings of 2026-10-10 implemented. (1) openalex.rebuild now reads an inverted-index key that holds whitespace (a paragraph break OpenAlex left in one token) as its words joined by one space at its one position; an empty or whitespace-only key, a gap and a conflict are still refused. (2) A cited [[duplicate_choice]] row in openalex_sources.toml (openalex_table.DuplicateChoice) pins W2796639635 for AIES 2019's 10.1145/3306618.3314250. The fill attaches that work alone, counting it in attached_doi and FillReport.duplicate_chosen, and stops with duplicate_choice_unmatched if the extract no longer answers the DOI with that work among two or more works. (3) Everything else stays refused, including FAccT 2021's duplicate and all 21 title_ambiguous (Shvaytser 1990 among them). Predicted with an offline fill of extract 7fea58b98325 over snapshot 2026-10-10-22a339940466; the snapshot is not rebuilt. By DOI 1,098 (1 chosen), by title 1,150 (+89); inverted_unreadable 2, inverted_gap 60, doi_duplicate 1. Docs updated: spec 01 (the OpenAlex row and §Pipeline fill report), the research note §OpenAlex (TASK-231), the milestone C plan and CLAUDE.md. Verified with the openalex tests (163 passed), the full backend suite (8,885 passed, 3 skipped) and make lint (clean).
<!-- SECTION:FINAL_SUMMARY:END -->
