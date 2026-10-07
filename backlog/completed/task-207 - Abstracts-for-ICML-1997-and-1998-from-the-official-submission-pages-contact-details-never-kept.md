---
id: TASK-207
title: >-
  Abstracts for ICML 1997 and 1998 from the official submission pages, contact
  details never kept
status: Done
assignee: []
created_date: '2026-10-07 13:59'
updated_date: '2026-10-07 15:14'
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
- [x] #1 icml_sites.toml lists the 1997 page and the 66 1998 pages as pinned Internet Archive captures of official sites, with charset and verified entry counts
- [x] #2 Parsers keep only the abstract section; an abstract that still holds an e-mail address, phone/fax number or postal code is withheld and counted, never stored or logged
- [x] #3 Tests show no contact detail from a 1997/1998 page reaches records, the snapshot, the index, exports or log lines
- [x] #4 Abstract provenance says submission-time abstract from the official page and names the capture timestamp
- [x] #5 decision-047, spec 01, the research survey and icml_sites.toml say 1997/1998 are used; decision-047 records the owner's confirmation of PR #120's labelling choices
- [x] #6 A new snapshot and index are built (current not repointed); the snapshot diff only adds abstracts to ICML 1997/1998 records; coverage gate passes; the Trust-Evals query returns the same 101 ids; no e-mail/phone pattern in ICML 1997/98 abstracts
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Survey the 1997/1998 official pages (ICML-97 program page linked from the ICML-97/COLT-97 schedule; ICML-98 per-submission pages named by icml.cc); add parsers that keep only the span after an Abstract heading up to the form's next field, re-check it for contact details and withhold whole on any hit or when no field ends it; table the 67 captures; say submission-time in the claim evidence and the coverage scope line; test every surface end to end; record the owner decision and PR #120 confirmations in decision-047; then build a snapshot and index (current not moved) and check the diff, coverage gate, Trust-Evals ids and a contact scan.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implementation: icml_sites.icml1997 (program page: list titles + per-anchor free text) and icml1998_paper (per-submission page; H1 number must equal the URL's) keep only the text after an Abstract heading up to the form's next field (keywords, e-mail, phone, ...); contact_detail() re-checks the kept text (e-mail, phone-shaped digits, contact labels, US ZIP) and withholds the whole abstract (site_withheld). Evidence says submission-time abstract + capture. OFFICIAL_SITES gains the Vanderbilt ~icml97 site (linked from the ICML-97/COLT-97 schedule) and cs.wisc.edu /icml98/ and /ICML98/ (icml.cc past-conferences). Manifest dblp listings gain site_withheld and abstracts_as_submitted; the coverage report's scope line names the submission-time abstracts. Dry run over the real captures: 1997 49 entries, 46 with abstracts (3 no heading), 40 match dblp titles; 1998 66 pages, 65 with abstracts (1 no heading), 51 match; 0 withheld. Unmatched are retitled papers (exact-key rule). Raw pages with contact details stay in the local HTTP cache (data/cache/icml_sites), as every fetched page does.

Data (2026-10-07): op ingest dblp --year 1997-1998 (67 requests, 0 retries); snapshot 2026-10-07-6adb465a519f, index 4646c7547fe7 (data/indexes/current left at 2b7f809e8668). Snapshot diff vs 2026-10-07-4063d9bc062c: 0 added/removed/rekeyed, 91 changed (abstract only; 1997: 40, 1998: 51; all null before). Coverage --check PASS (71/72, 1 accepted exception). Trust-Evals first line, --mode scholar --ids: 101 ids, identical on both indexes. Contact scan of the 114 ICML 1997/98 records: no e-mail, phone, label, ZIP or URL pattern. Results: docs/results/2026-10-07-icml-1997-1998-abstracts.md. Proposed follow-up (no id: TASK-208 is reserved by a parallel branch): label submission-time abstracts in exports (RIS N1, CSV abstract_source) and the results list, not only in the claim evidence and coverage report (ux-reviewer, review-methodologist).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
ICML 1997 and 1998 now take abstracts from their official pages (the ICML-97 program page and the 66 ICML-98 submission pages, pinned Internet Archive captures). Parsers icml1997/icml1998_paper keep only the abstract (after the Abstract heading, up to the form's next field: keywords, contact, address, author fields); contact_detail re-checks the kept text (e-mail, phone-shaped numbers, contact labels, postal codes, street addresses) and the abstract is withheld whole on any hit or when no field ends it (site_withheld). Claims say submission-time abstract from the official page with the capture timestamp; the manifest marks abstracts_as_submitted and the coverage report's scope line counts them. Captures are judged whole by Content-Length (27 of 66 1998 pages and the 1997 page lack </html>). decision-047 records the owner decision and confirms PR #120's labelling choices. Verified: test_icml_submissions.py runs ingest, replay, snapshot, index, every export and raw log records for both years against invented contact details; full make test/lint/tooling green; new snapshot 2026-10-07-6adb465a519f / index 4646c7547fe7: diff adds 91 abstracts (1997: 40, 1998: 51) and nothing else, coverage gate PASS, Trust-Evals 101 ids unchanged, no contact pattern in the 1997/98 abstracts.
<!-- SECTION:FINAL_SUMMARY:END -->
