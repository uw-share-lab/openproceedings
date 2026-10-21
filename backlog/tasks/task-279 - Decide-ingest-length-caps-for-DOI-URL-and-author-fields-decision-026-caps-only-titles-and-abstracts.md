---
id: TASK-279
title: >-
  Decide: ingest length caps for DOI, URL and author fields (decision-026 caps
  only titles and abstracts)
status: To Do
assignee: []
created_date: '2026-10-21 23:01'
updated_date: '2026-10-21 23:01'
labels:
  - ingest
  - security
dependencies: []
priority: low
ordinal: 185000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-274. ingest/record.py validates a DOI's shape (10.NNNN/suffix, one line) and a URL's (http(s), a host, one line) but caps neither's length, and author names are uncapped too; decision-026 (ingest/caps.py) caps only titles (1,000 characters) and abstracts (20,000). Since TASK-274 the BibTeX export escapes every field in linear time, and doi, url and author all go through export._braced, so a long value no longer costs quadratic CPU; but a record's DOI, URL or author list of any length is still stored and written whole into every export format and API response. These fields come from crawled sources (Crossref, OpenAlex, OpenReview, proceedings pages, the RIS cache), not from the reviewer. Decide whether to cap them at ingest (refuse or trim, flagged as decision-026 does) and at what lengths, or record why not.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decision record says whether DOI, URL and author fields are capped at ingest, at what lengths and whether over-cap values are refused or trimmed (and flagged), or why they are left uncapped
- [ ] #2 If capped: ingest/caps.py applies the caps with tests, and the record-schema skill and spec 01 describe them
<!-- AC:END -->
