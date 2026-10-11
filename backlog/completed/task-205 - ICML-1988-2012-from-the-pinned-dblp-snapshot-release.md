---
id: TASK-205
title: ICML 1988-2012 from the pinned dblp snapshot release
status: Done
assignee: []
created_date: '2026-10-07 03:15'
updated_date: '2026-10-07 05:44'
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
- [x] #1 A data table names the pinned release (DOI, URL, size, sha256, DTD) and per ICML year the dblp proceedings key(s) that are the main conference, with verified counts
- [x] #2 A streaming parser selects the ICML main-conference inproceedings without loading the 1.1 GB file into memory; the release is downloaded through the shared HTTP layer's host allowlist and verified by sha256
- [x] #3 Records are ICML year/main/accepted with title, authors, ee urls, abstract null, every claim naming the release DOI
- [x] #4 op ingest dblp exists per spec 01; dedup never merges a dblp record across sources wrongly (no overlap with PMLR 2013+, verified)
- [x] #5 Missing abstracts are visible to a reviewer (coverage page, manifest counts)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Pin the DROPS release 10.4230/dblp.xml.2026-10-03 and its DTD by DOI/size/sha256 (dblp_icml.toml); download through http.fetch_file; stream conf/icml/ records (dblp_xml.py) into an extract keyed by the release sha256; classify every conf/icml proceedings key of 1988-2012 as main or excluded; mine records (dblp.py); op ingest dblp; replay from the extract in op snapshot build.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Release: 1,107,081,001 bytes, sha256 20e45961bec5610dc07b8e932ccd27a2387534cfa12c92a24289fe873aebe969 (md5 cbd329100ea1bbb2873fa2f6d414ea00). 17,115 conf/icml records read in ~75 s. 2,676 main papers 1988-2012, 2,675 records (2009: 1 withdrawn). Excluded keys: 2006sna, 2010ltr, 2011otee, 2011utl. dedup over the 2,675 gives no merge and no conflict; dblp ids are bounded to ICML 1988-2012 in the record model, so PMLR (2013+) never overlaps. Missing abstracts are shown per venue-year on the coverage page (No abstract column, all-missing flag) and per year in the dblp report; the coverage page now also names each venue's year span (CV-7). Focused review fixes: scholar_compare.proceedings_key no longer asserts on a dblp URL; takedowns treat dblp ids as global; check_extract refuses an unclassified proceedings record with no year; replay refuses a year marked under another release; a stale extract is rewritten; an oversize download is refused at once; the release's encoding declaration is checked.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
ICML 1988-2012 come from dblp release 10.4230/dblp.xml.2026-10-03 (sha256 20e45961...aebe969), pinned with its DTD in ingest/dblp_icml.toml and downloaded from drops.dagstuhl.de through http.fetch_file (dblp.org never fetched). dblp_xml.py streams the 1.1 GB file (~75 s) into an extract keyed by the release sha256; snapshot builds replay the extract only. 2,675 records (main/accepted, title, authors, DOI/PDF, the dblp record page as urls.proceedings; every claim names the release); workshop keys are excluded by the table and an unclassified key stops the ingest. op ingest dblp; record schema 5 (sources dblp and icml_site, dblp-<key> ids bounded to 1988-2012, so no overlap with PMLR); dedup over the records merges nothing. Missing abstracts: per year in the dblp report, per venue-year on the coverage page, which now also names each venue's year span (CV-7). Tests: test_dblp.py, test_dblp_xml.py, the contract additive test for open-enum arrays; make test, lint and tooling pass.
<!-- SECTION:FINAL_SUMMARY:END -->
