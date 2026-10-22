---
id: TASK-279
title: >-
  Decide: ingest length caps for uncapped stored string fields (DOI, URLs,
  authors, keywords, venue_id_raw, claim url and evidence)
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-10-21 23:01'
updated_date: '2026-10-22 05:30'
labels:
  - ingest
  - security
dependencies: []
priority: low
ordinal: 185000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-274. decision-026 (ingest/caps.py, CAPPED = title, abstract) caps only titles (1,000 characters) and abstracts (20,000). Every other stored string field is uncapped: ingest/record.py validates a DOI's shape (10.NNNN/suffix, one line) and each URL's (http(s), a host, one line) but not their length; author names, keywords and venue_id_raw have no cap; nor do provenance claims' url and evidence (Claim.url, Claim.evidence), which snapshots store and the API shows. Since TASK-274 the BibTeX export escapes every field in linear time (doi, url and author all go through export._braced), so a long value no longer costs quadratic CPU; what remains is size: a value of any length is stored and written whole into every export format (BibTeX, RIS, CSV, JSONL) and API response. These fields come from crawled sources (Crossref, OpenAlex, OpenReview, proceedings pages, the RIS cache), not from the reviewer. Decide whether to cap them at ingest (refuse or trim, flagged as decision-026 does) and at what lengths, or record why not.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A decision record says, for each uncapped stored string field (DOI, URLs, authors, keywords, venue_id_raw, claim url and evidence), whether it is capped at ingest, at what length and whether an over-cap value is refused or trimmed (and flagged), or why it is left uncapped
- [ ] #2 If capped: ingest/caps.py applies the caps with tests, and the record-schema skill and spec 01 describe them
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Measure each uncapped stored string field's real maximum over snapshot 2026-10-16-03eab0ef56c4 (read-only) and pick caps with generous headroom so no current record is trimmed.
2. Owner decision 2026-10-22: cap + trim (decision-026's model), trimmed and flagged, never refused. Write the decision record (created last, after rebasing): per field cap, trim and flag; a cut DOI or URL is never used as an identifier (the record's urls slot is cleared, dedup's resolve and identity reads skip a cut urls.* claim, a cut claim url is dropped) and is kept only as display text in its claim.
3. ingest/caps.py: MAX_DOI, MAX_URL, MAX_AUTHOR, MAX_KEYWORD, MAX_VENUE_ID, MAX_INVITATION, MAX_EVIDENCE; cut as decision-026 cuts (NFKD length, before the last space); a second note form 'trimmed at ingest (decision-NNN):'; is_trimmed covers both; dedup skips cut identifiers.
4. Tests: per field at cap-1, cap, cap+1; Hypothesis property; flag presence; dedup skip; snapshot build with an over-cap DOI.
5. Docs as built: record-schema and snapshots skills, spec 01, CLAUDE.md layout line, decision-026 cross-reference.
6. Verify no version bump needed (caps return records unchanged within them), make test/lint/tooling, learnings, review gate, finalize, PR, merge queue.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Measured over snapshot 2026-10-16-03eab0ef56c4 (173,518 records, every claim): DOI 34, URL 154 (claim url 154), author 81, keyword 733 (an abstract split into keywords, ICLR 2025 d8hURACo0P), venue_id_raw 65, invitation none, evidence 469, id 53; at most 95 authors and 54 keywords per record. Caps: DOI 1,000, URL and claim url 2,048, author 1,000, keyword 2,000, venue_id_raw and invitation 500, evidence 4,000 (notes included). cap_record over every record of that snapshot returned each unchanged (changed=0; the 26 decision-026 already lists stay), so records.jsonl, snapshot_hash and index_version are unchanged: no RECORD_SCHEMA_VERSION, TOKENIZER_VERSION or SCHEMA_VERSION bump (the caps belong to the build, as decision-026's do). A cut URL whose cut changed what it names is not read as an id (unread_identifier); one whose cut left it alone still names its paper, so a long query string never refuses the build at dedup's self-naming check. Local: make test (9205 passed, 3 skipped; frontend 4954 passed), make lint, make tooling green; mutate-changed: no mutants cover the diff. Follow-up (file at the end): cap the number of authors and keywords per record.
<!-- SECTION:NOTES:END -->
