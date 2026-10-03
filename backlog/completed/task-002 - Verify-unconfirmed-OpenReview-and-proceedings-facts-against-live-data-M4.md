---
id: TASK-002
title: Verify unconfirmed OpenReview and proceedings facts against live data (M4)
status: Done
assignee: []
created_date: '2026-09-25 22:06'
updated_date: '2026-09-27 20:48'
labels:
  - ingest
milestone: m-4
dependencies: []
references:
  - .claude/skills/openreview-venueids/SKILL.md
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The ingestion skills mark these 'verify'. Confirm each with recorded fixtures before writing classifiers.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 venueid forms confirmed with a recorded example each: Desk_Rejected, bare /Submission, D&B 2024+ without Track/, 2021 D&B Round1/Round2, ICML and NeurIPS position tracks, Tiny Papers, Blogposts, Competition
- [x] #2 PMLR volumes for ICML 2025+ and competition/workshop volumes added to the volume table with sources
- [x] #3 Whether NeurIPS 2021 D&B has a separate proceedings host
- [x] #4 OpenReview max page size and .env variable names confirmed
- [x] #5 openreview-venueids, pmlr-proceedings and neurips-proceedings skills updated; the 'verify' markers removed
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Manual live run 2026-09-27 (authenticated; ~450 OpenReview + ~35 proceedings requests, paced 1 per 2 s). Evidence: docs/research/2026-09-27-openreview-and-proceedings-facts.md. Fixtures: backend/tests/fixtures/http/{openreview/v1,openreview/v2,neurips,pmlr}/ (53 files) made by backend/tests/fixtures/http/scrub.py (no network code; decision-004 scrubbing). AC1: every form has a fixture or checked id; bare /Submission has no public note on any decided venue, so it is evidenced by the groups' submission_venue_id (group-conference.json). AC2: volume table lives in the pmlr-proceedings skill with sources; ICML v28-v97 and NeurIPS competition volumes go into code with TASK-053's config (volumes.py is ICML-only and pinned by test_ris.py). AC4: limit <= 1000 on both hosts; count only with offset on v2; env names OPENREVIEW_USERNAME/OPENREVIEW_PASSWORD. Key findings: anonymous access gets an HTML challenge with HTTP 200; v1 venueids are not status evidence (TASK-091); NeurIPS Position/Competition tracks unmapped in classify.py (TASK-090); ICLR 2014/2015/2016 gaps (TASK-092).

Worktree sandbox refused 'backlog task complete' (2026-09-27); all ACs ticked and final summary written — main session: set Done and complete after merge.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Verified every 'verify' fact live and recorded them in docs/research/2026-09-27-openreview-and-proceedings-facts.md: API version per venue-year from 2013, venueid forms (desk-rejected, D&B without Track/, 2021 Round1/2, ICML and NeurIPS position, Tiny Papers, BlogPosts, Competition), status carriers per v1 year, public-status policy per venue, auth (anonymous gets an HTML challenge), limit 1000 and count-with-offset, NeurIPS proceedings URL grammar per year and the separate 2021 D&B host, PMLR ICML volumes v28-v267 with counts. 53 scrubbed fixtures under backend/tests/fixtures/http/. openreview-api, openreview-venueids, neurips-proceedings, pmlr-proceedings (and track-taxonomy, coverage-reporting) skills and spec 01 updated; verify markers removed. Follow-ups TASK-090, 091, 092.
<!-- SECTION:FINAL_SUMMARY:END -->
