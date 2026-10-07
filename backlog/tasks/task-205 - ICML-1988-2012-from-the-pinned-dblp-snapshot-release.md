---
id: TASK-205
title: ICML 1988-2012 from the pinned dblp snapshot release
status: To Do
assignee: []
created_date: '2026-10-07 03:15'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 148000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PMLR starts at ICML 2013 (v28) and the earlier proceedings are scattered (ACM DL 2004-2008, Morgan Kaufmann print before). dblp lists them, but dblp.org forbids crawling (robots.txt Disallow: /, Anubis challenge); its sanctioned bulk route is the monthly snapshot XML release on Dagstuhl DROPS (CC0, one DOI per release). Pinning one release by DOI and sha256 keeps the ICML records reproducible (guarantee 4). dblp has no abstracts.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A data table names the pinned release (DOI, URL, size, sha256, DTD) and per ICML year the dblp proceedings key(s) that are the main conference, with verified counts
- [ ] #2 A streaming parser selects the ICML main-conference inproceedings without loading the 1.1 GB file into memory; the release is downloaded through the shared HTTP layer's host allowlist and verified by sha256
- [ ] #3 Records are ICML year/main/accepted with title, authors, ee urls, abstract null, every claim naming the release DOI
- [ ] #4 op ingest dblp exists per spec 01; dedup never merges a dblp record across sources wrongly (no overlap with PMLR 2013+, verified)
- [ ] #5 Missing abstracts are visible to a reviewer (coverage page, manifest counts)
<!-- AC:END -->
