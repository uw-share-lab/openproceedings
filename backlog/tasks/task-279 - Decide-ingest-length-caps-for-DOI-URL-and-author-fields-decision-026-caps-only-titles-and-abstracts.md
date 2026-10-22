---
id: TASK-279
title: >-
  Decide: ingest length caps for uncapped stored string fields (DOI, URLs,
  authors, keywords, venue_id_raw, claim url and evidence)
status: In Progress
assignee:
  - '@jeevan'
created_date: '2026-10-21 23:01'
updated_date: '2026-10-22 05:03'
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
