---
id: TASK-051
title: OpenReview API v1 adapters per year
status: Done
assignee: []
created_date: '2026-09-26 01:06'
updated_date: '2026-09-29 01:35'
labels:
  - ingest
milestone: m-4
dependencies:
  - TASK-048
  - TASK-049
  - TASK-050
ordinal: 50000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
ICLR 2013, 2014, 2016-2023 (decision-013 moved the start from 2018) and NeurIPS 2021-2022 incl. D&B; decisions as separate notes or venue strings. Per-year status carriers are in the openreview-api skill §API v1 (TASK-002).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 One adapter per schema variant with a recorded fixture
- [x] #2 Rejected/withdrawn statuses captured (decision per task q2-status)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK-002: the bare v1 venueid is on rejected papers too (ICLR 2017/2022/2023, NeurIPS 2021-22, D&B 2021) — status only from content.venue / decision note / withdrawn and desk-rejected invitations (TASK-091). ICLR 2013 status+track from content.decision; 2014 and 2016 have no decisions (unknown). v1 invitation filters must be prefix regexes; fetch decisions per forum. Fixtures: backend/tests/fixtures/http/openreview/v1/.

Renumbered 2026-09-27 (parallel-branch id collision): TASK-090 → TASK-094, TASK-091 → TASK-095, TASK-092 → TASK-096 in the notes above.

From TASK-095: the withdrawn ICLR 2021 note xGZG2kS5bFk has an accepted-sounding content.venue; the v1 adapter must record the withdrawn invitation vs venue string as a conflict, not accept it.

Built (branch t051 off feat/m4-crawlers): ingest/sources/openreview_v1.py with ADAPTERS, one Adapter per venue-year (ICLR 2013-2023 incl. an empty 2015, NeurIPS 2021-2022 incl. D&B): exact listing invitations (submission / withdrawn / desk-rejected, each with the track submitted to), status from content.decision (2013), none (2014, 2016: unknown), content.venue via classify_v1_venue (2017, 2022, 2023, NeurIPS), the per-forum decision note (2018-2020; 2021 notes without a venue string) or the withdrawn / desk-rejected invitation; never the v1 venueid (it only confirms venue/year and must agree with the decided track). Coverage gaps (2014 no decisions, 2015 no group, 2016 workshop only, 2023 Blogposts, NeurIPS withdrawn/desk-rejected) are in each report's coverage_gaps, not errors. xGZG2kS5bFk: status unknown + an unresolved:openreview_v1 row in conflicts.csv (snapshot.with_crawl_conflicts, re-pointed along merges). Client: login_base (v1 client logs in on api2), cache under cache/openreview/v1/http. op ingest openreview sends each year to v1 or v2 (openreview_v1.api_for); snapshot build replays both. Tests: test_openreview_v1.py (33, one replay per adapter from the recorded v1 fixtures with FakeOpenReviewV1 + FakeClock). uv run pytest: 3908 passed, 2 skipped.

AC #2 left open, needs live recording: NeurIPS 2021/2022 withdrawn and desk-rejected invitations (not crawled until one is verified), and ICLR 2020/2021 accept decision strings (only Reject is recorded; accepted 2020 notes are unknown + counted in unmapped). Fixtures to record live: an ICLR 2020 accepted forum (Paper<N>/-/Decision), an ICLR 2021 accepted decision note, one ?invitation= listing page per v1 year (only 2013/2014/2016/2023-Blind listing pages are recorded; the rest are single notes by id), an ICLR 2018/2019/2020 Withdrawn_Submission note, an ICLR 2020/2021/2022 Desk_Rejected note, ICLR 2017 workshop-invitation note (its venue string), ICLR 2023 Blogposts note + its invitation, NeurIPS 2021/2022 Withdrawn_Submission/Desk_Rejected_Submission listings (or proof they are empty/absent), NeurIPS 2022 D&B note, and an unscrubbed-shape ICLR 2017 authors string. Unverified: the v1 sort parameter (listings use none; rows == ids == count guards).

TASK-107 (2026-09-29) recorded and scrubbed the missing authenticated v1 evidence: one listing response per v1 venue-year with a group; ICLR 2018-2020 withdrawn and 2020-2022 desk-rejected listings; public ICLR 2020/2021 Accept (Poster) decision forums; ICLR 2017 workshop and authors-string shapes; ICLR 2023 BlogPosts; NeurIPS 2021/2022 main withdrawn/desk-rejected queries (all count 0); and NeurIPS 2022 D&B. Adapters now crawl BlogPosts and the verified-empty NeurIPS status invitations and map both recorded accept decisions. Validation: 278 targeted OpenReview tests; full backend 5100 passed, 2 skipped; make tooling and make lint passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Completed the API v1 adapter matrix for ICLR 2013-2023 and NeurIPS 2021-2022, including explicit rejected, withdrawn and desk-rejected coverage, ICLR 2020/2021 accepted decisions, ICLR 2023 BlogPosts and NeurIPS D&B. Every live shape has a scrubbed fixture; public-empty NeurIPS status listings are crawled and reported as zero. Verified by 278 targeted tests, the full backend suite (5100 passed, 2 skipped), tooling, lint and strict typing.
<!-- SECTION:FINAL_SUMMARY:END -->
