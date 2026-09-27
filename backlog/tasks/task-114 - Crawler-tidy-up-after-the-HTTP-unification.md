---
id: TASK-114
title: Crawler tidy-up after the HTTP unification
status: In Progress
assignee: []
created_date: '2026-09-27 23:24'
updated_date: '2026-09-27 23:35'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 111000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-ups from TASK-103 and TASK-105: (1) move the per-source ingest loop (lock, crawl, write marker) into sources/common beside the shared replay; (2) delete the per-source HTTP-property tests in test_fetch.py and test_openreview_client.py that test_http.py now covers once for all sources; (3) make pmlr._forum call urls.forum_id so there is one forum-id parser. Behaviour-preserving: test_combined_snapshot.py's pinned hashes must not change.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 One ingest loop in common used by all four sources,Duplicate HTTP-property tests removed with test_http.py covering each property,pmlr uses urls.forum_id,test_combined_snapshot hashes unchanged
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Crawls.ingest in sources/common is now the one op ingest loop (lock on the source dir, crawl each key, write the finished crawl's marker in the directory replay reads); openreview_v1/v2.ingest and crawl.ingest_neurips/ingest_pmlr call it. test_http.py gained parametrized pacing and offline-miss tests for all three sources; the duplicate allowlist, off-host redirect, pacing and offline-miss tests in test_fetch.py and the pacing test in test_openreview_client.py are gone (per-source retry policy tests stay). pmlr uses urls.forum_id (pmlr._forum deleted; the one difference: forum_id also requires an http(s) scheme, and PMLR hrefs are urljoin'd against an https base). test_combined_snapshot.py untouched and passing (pinned hashes unchanged). http.py not edited. Full pytest 4066 passed, make lint and make tooling green.
<!-- SECTION:FINAL_SUMMARY:END -->
