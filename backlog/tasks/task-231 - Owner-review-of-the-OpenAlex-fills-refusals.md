---
id: TASK-231
title: Owner review of the OpenAlex fill's refusals
status: To Do
assignee: []
created_date: '2026-10-11 00:15'
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
- [ ] #1 The 2 doi_duplicate DOIs are listed with each work's text, and the owner picks one, or confirms the refusal
- [ ] #2 The 21 title_ambiguous cases are listed and each is attached by hand-checked evidence or confirmed refused
- [ ] #3 The 117 AAAI works refused for line breaks in their index keys are listed, and the owner decides to split or strip such keys, or to keep refusing
- [ ] #4 Any change to the rules is made in sources/openalex.py with its tests and spec 01, and the outcome is recorded in the OpenAlex row of spec 01
<!-- AC:END -->
