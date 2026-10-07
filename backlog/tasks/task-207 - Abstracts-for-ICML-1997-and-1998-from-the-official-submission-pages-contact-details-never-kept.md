---
id: TASK-207
title: >-
  Abstracts for ICML 1997 and 1998 from the official submission pages, contact
  details never kept
status: In Progress
assignee: []
created_date: '2026-10-07 13:59'
updated_date: '2026-10-07 13:59'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 146000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-206 skipped ICML 1997 and 1998: their official pages (the ICML-97 program page at Vanderbilt, linked paper by paper from the ICML-97/COLT-97 schedule; the ICML-98 site's per-submission pages at cs.wisc.edu/icml98/, named by icml.cc's past-conferences pages) hold submission-time abstracts beside the authors' postal addresses, e-mail addresses and phone/fax numbers. The owner decided (2026-10-07) to use them: keep only the abstract text, strip every contact detail so none reaches the snapshot, index, exports or logs (tested), and say in provenance that these are submission-time abstracts from the official page, with the capture timestamp. Same owner message: record in decision-047 the confirmed labelling choices from PR #120 (1989/1991/1992 indexed as ICML; ICML 2010 invited application papers main; the 27 non-papers track other).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 icml_sites.toml lists the 1997 page and the 66 1998 pages as pinned Internet Archive captures of official sites, with charset and verified entry counts
- [ ] #2 Parsers keep only the abstract section; an abstract that still holds an e-mail address, phone/fax number or postal code is withheld and counted, never stored or logged
- [ ] #3 Tests show no contact detail from a 1997/1998 page reaches records, the snapshot, the index, exports or log lines
- [ ] #4 Abstract provenance says submission-time abstract from the official page and names the capture timestamp
- [ ] #5 decision-047, spec 01, the research survey and icml_sites.toml say 1997/1998 are used; decision-047 records the owner's confirmation of PR #120's labelling choices
- [ ] #6 A new snapshot and index are built (current not repointed); the snapshot diff only adds abstracts to ICML 1997/1998 records; coverage gate passes; the Trust-Evals query returns the same 101 ids; no e-mail/phone pattern in ICML 1997/98 abstracts
<!-- AC:END -->
