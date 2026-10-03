---
id: TASK-018
title: 'PaperRecord model, content_hash and provenance claims'
status: Done
assignee:
  - '@jeevan'
created_date: '2026-09-26 01:06'
updated_date: '2026-09-26 18:34'
labels:
  - ingest
milestone: m-2
dependencies:
  - TASK-009
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Spec 01 §Record schema (record-schema skill).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 pydantic v2 model with every spec 01 field; id scheme op:<venue>:<year>:<native>
- [x] #2 content_hash over searchable and filterable fields only (provenance excluded)
- [x] #3 Claims ledger per field (source, url, fetched_at, evidence)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verification round (2026-09-26): the hash is recomputed only when build/model_copy ask through the validation context (a stored 'pending' can no longer rehash a tampered line); every string field is valid Unicode; title has no control characters, abstract no outer whitespace; a claim's value must fit its field; forum-id natives 4-64 chars with an alphanumeric; rows for every surviving mutant.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PaperRecord/Claim/Urls/content_hash (ingest/record.py) and the Literal vocab (vocab.py): frozen, strict records whose id, native-id form, snippet rule, claim order and hash are enforced on every construction and load; the hash is recomputed only on request from build/model_copy. Verified: 90 unit tests, two review rounds with mutation passes (every non-equivalent mutant killed), JSON round-trip and 50k-record validation timing.
<!-- SECTION:FINAL_SUMMARY:END -->
