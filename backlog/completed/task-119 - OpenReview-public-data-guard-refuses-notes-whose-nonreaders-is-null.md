---
id: TASK-119
title: OpenReview public-data guard refuses notes whose nonreaders is null
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-29 06:10'
updated_date: '2026-09-29 06:36'
labels:
  - ingest
  - bug
milestone: m-4
dependencies: []
priority: high
ordinal: 114000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The first live crawl (2026-09-29) stopped at ICLR 2017: op ingest openreview refused with private_response. 59 of the 161 ICLR.cc/2017/workshop/-/submission notes have readers ['everyone'] and nonreaders null (the other 102 have []); _world_readable requires nonreaders to be a list, so it failed closed on public notes and aborted the ICLR crawl for 2017 onwards. A null nonreaders excludes no one.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 _world_readable treats nonreaders null exactly as absent or []; any other non-list value, and every non-public ACL, still refuses
- [x] #2 A regression with nonreaders null passes the projection and is ingested; the existing refusal cases still refuse
- [x] #3 The openreview-api skill documents the null form
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
_world_readable now treats nonreaders null exactly like absent or []: API v1 writes null on public notes (59 of 161 live ICLR 2017 workshop submissions, all readers ['everyone']), and the guard had failed closed, aborting the ICLR OpenReview crawl from 2017. Only None is accepted; '', {}, False, 0 and other non-lists still refuse (pinned), as does any private ACL with null nonreaders. No projection-version bump: the rule only admits pages the old one refused and never cached. Tests: client-level null/[]/absent and refusal cases, and a derived v1 ingest case; make test 5158 passed, 2 skipped; frontend 2582; lint and tooling clean.
<!-- SECTION:FINAL_SUMMARY:END -->
