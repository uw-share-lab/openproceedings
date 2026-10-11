---
id: TASK-229
title: >-
  Lone UTF-16 surrogates in any source's abstract: one shared decision before
  the record is built
status: Done
assignee: []
created_date: '2026-10-10 17:22'
updated_date: '2026-10-10 20:25'
labels:
  - ingest
dependencies: []
ordinal: 159000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From milestone C Task 7 review (2026-10-10). A JSON-escaped lone surrogate (\ud800) passes clean_abstract/abstract_text and only fails later at record._utf8, which stops the whole crawl. OpenAlex refuses such an abstract itself (abstract_unusable); the other JSON/XML sources do not. Changing the shared clean step to drop them would turn a loud stop into a silently missing abstract, so decide per source (refuse the claim and count it, or stop) and pin it with tests.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every source's handling of a lone surrogate in an abstract is decided, tested, and documented in spec 01
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decision (one rule for every source): a lone UTF-16 surrogate in an abstract refuses that abstract claim; the paper is kept on its title; the source's report counts it as abstract_surrogate (site_surrogate for an official ICML/FAccT page row; OpenAlex refused[abstract_surrogate]); a DEBUG abstract_surrogate_refused line names source + record, never the text. Shared step: common.clean_abstract (Cleaned.refused) + missing_reason; openreview_v2._abstract (v1 and v2); ris._abstract (passes over the refused claim to the next, like an empty one). Found: the OpenReview response cache (EntryCodec holds parsed JSON) crashed with UnicodeEncodeError on writing such a note, so the crawl stopped before any rule; http.ResponseCache.put now writes that entry as ASCII JSON (every other entry's bytes unchanged). Before: OpenReview stopped (cache write), PMLR/NeurIPS/OJS/dblp skipped the whole paper as invalid, Crossref/FAccT stopped (invalid_record), RIS stopped. Titles unchanged and loud everywhere (invalid or stop). HTML/XML sources cannot produce one (U+FFFD / expat refuses / strict decoding).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Every source now refuses an abstract holding a lone UTF-16 surrogate, keeps the paper on its title and counts it as abstract_surrogate (site_surrogate for official-page rows) instead of stopping the crawl or dropping the paper; the OpenReview response cache keeps such an entry escaped instead of crashing. Spec 01 §Pipeline 2 has the per-source table; record-schema, openreview-api and logging-standards skills updated. Verified: backend/tests/unit/ingest/test_abstract_surrogates.py (one test per source plus titles, cache and reachability), full backend suite and make lint green; no golden or snapshot output changed.
<!-- SECTION:FINAL_SUMMARY:END -->
