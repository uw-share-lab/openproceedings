---
id: TASK-279
title: >-
  Decide: ingest length caps for uncapped stored string fields (DOI, URLs,
  authors, keywords, venue_id_raw)
status: To Do
assignee: []
created_date: '2026-10-21 23:01'
updated_date: '2026-10-21 23:09'
labels:
  - ingest
  - security
dependencies: []
priority: low
ordinal: 185000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-274. decision-026 (ingest/caps.py, CAPPED = title, abstract) caps only titles (1,000 characters) and abstracts (20,000). Every other stored string field is uncapped: ingest/record.py validates a DOI's shape (10.NNNN/suffix, one line) and each URL's (http(s), a host, one line) but not their length, and author names, keywords and venue_id_raw have no cap either. Since TASK-274 the BibTeX export escapes every field in linear time (doi, url and author all go through export._braced), so a long value no longer costs quadratic CPU; what remains is size: a value of any length is stored and written whole into every export format (BibTeX, RIS, CSV, JSONL) and API response. These fields come from crawled sources (Crossref, OpenAlex, OpenReview, proceedings pages, the RIS cache), not from the reviewer. Decide whether to cap them at ingest (refuse or trim, flagged as decision-026 does) and at what lengths, or record why not.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decision record says, for each uncapped stored string field (DOI, URLs, authors, keywords, venue_id_raw), whether it is capped at ingest, at what length and whether an over-cap value is refused or trimmed (and flagged), or why it is left uncapped
- [ ] #2 If capped: ingest/caps.py applies the caps with tests, and the record-schema skill and spec 01 describe them
<!-- AC:END -->
