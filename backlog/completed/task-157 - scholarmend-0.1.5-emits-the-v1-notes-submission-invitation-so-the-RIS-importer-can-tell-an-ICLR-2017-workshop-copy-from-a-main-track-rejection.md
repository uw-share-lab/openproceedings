---
id: TASK-157
title: >-
  scholarmend 0.1.5 emits the v1 note's submission invitation so the RIS
  importer can tell an ICLR 2017 workshop copy from a main-track rejection
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-10-02 00:40'
updated_date: '2026-10-02 07:25'
labels:
  - ingest
milestone: m-4
dependencies: []
references:
  - backend/src/openproceedings/ingest/ris.py
  - backend/src/openproceedings/ingest/sources/openreview_v1.py
  - backend/src/openproceedings/ingest/classify.py
  - docs/results/2026-10-01-iclr-2017-workshop-copies.md
  - .claude/skills/openreview-venueids/SKILL.md
  - .claude/skills/record-schema/SKILL.md
ordinal: 132000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: a TASK-152 (PR #63) deferral (its final summary; `docs/results/2026-10-01-iclr-2017-workshop-copies.md` §The RIS path). Cross-repo: a scholarmend release plus its pin here (`backend/pyproject.toml`, `scholarmend==0.1.4` today; 0.1.4 added the `venue_string` claim for TASK-098). TASK-152 made the v1 crawler read a main-track outcome on a note of a non-main submission listing, where the venueid names no track, as its conference twin's: the 18 ICLR 2017 workshop-listing notes whose `content.venue` is "Submitted to ICLR 2017" become workshop/`unknown`. The RIS importer could not follow: scholarmend's claims for a v1 note are only `venueid`, the forum id and `venue_string`, and a workshop copy's equal those of the 245 real main-track rejections (`ICLR.cc/2017/conference`, "Submitted to ICLR 2017"). So the importer still reads a copy as `main`/`rejected`. In a snapshot that also has the ICLR 2017 v1 crawl the crawl's track and status win by forum-id merge (decision-005, `precedence:openreview_v1` rows), but an RIS-only snapshot over-counts ICLR 2017 main/rejected by up to 18. The note's submission invitation (`ICLR.cc/2017/workshop/-/submission` vs `ICLR.cc/2017/conference/-/submission`) is what tells them apart.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 scholarmend 0.1.5 is released (PyPI, Trusted Publishing) and its resolved.json carries a v1 OpenReview note's submission invitation as a claim, with tests in scholarmend over a v1 note from each ICLR 2017 listing
- [x] #2 This repo pins `scholarmend==0.1.5` in `backend/pyproject.toml` and `uv.lock`, and every existing RIS importer test passes unchanged on the new version
- [x] #3 The RIS importer reads the invitation claim the way `openreview_v1.judge` reads the listing, and only where the venueid names no track: an RIS entry for `rkB_5hEKe` (added via `backend/tests/fixtures/ris/generate.py`, its claims matching the recorded note `backend/tests/fixtures/http/openreview/v1/iclr-2017/note-workshop-submitted-to-iclr-live.json`) imports as workshop/`unknown`, a real ICLR 2017 main-track rejection still imports as `main`/`rejected`, and an entry without the claim (an older resolved.json) keeps today's reading; each case is a test
- [x] #4 A test gives the recorded note to the v1 crawler, and the claims scholarmend 0.1.5 builds from it to the RIS importer, and asserts the same track and status (the per-path agreement TASK-152 AC #2 met only at the snapshot level)
- [x] #5 The claim's provenance is recorded on the record, and spec 01 (RIS row), the record-schema and openreview-venueids skills and the ris-importer agent no longer describe the RIS over-count as open
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC #1: done in the scholarmend repo by the lead (release v0.1.5 on PyPI via Trusted Publishing). It emits field invitation, source openreview_api, tier 2, evidence venueid=<note venueid>, with the v1 note's top-level invitation verbatim. v2 notes and older cache entries get none. The security review diffed the 0.1.4 and 0.1.5 wheels: only _version.py, ledger.py and resolvers/openreview.py differ. The PyPI attestation is from uw-share-lab/scholarmend release.yml.
AC #2: scholarmend==0.1.5 is pinned in backend/pyproject.toml and uv.lock (uv lock --check passes). Every existing RIS test passes, except that test_report_is_consistent_and_manifest_ready's pin of parser_version now reads 0.1.5.
AC #3: ris._invitation reads the claim only when every such claim holds one non-empty string and its evidence names the record's venueid. ris._twin_outcome applies the crawler's own rule (openreview_v1.is_twin_outcome, submission_listing; factored out of judge). Rows in backend/tests/fixtures/ris/generate.py (v1/), each a case of test_a_v1_invitation_tells_a_workshop_copy_from_a_main_track_rejection:
  - rkB_5hEKe, the recorded workshop copy: workshop/unknown;
  - a real rejection with the conference invitation: main/rejected;
  - a poster with the workshop invitation: workshop/unknown;
  - an unlisted invitation: kept, not used;
  - an invitation of another venueid: ignored;
  - no claim (an older entry): today's reading;
  - two different invitations, or an empty one: none;
  - a v2 invitation: ignored (test_an_invitation_outside_the_v1_years_is_ignored).
AC #4: test_the_crawler_and_the_ris_importer_read_a_workshop_copy_alike gives the recorded note to the v1 crawler and its scholarmend 0.1.5 claims (row 15) to the RIS importer. Both give workshop/unknown and the same id.
AC #5: an invitation claim (source ris, evidence scholarmend:openreview_api venueid=<id>) is kept on the record. Updated: spec 01 RIS row, record-schema, openreview-venueids and openreview-api skills, the ris-importer agent. Decision-029 covers this task and TASK-159.
Real data: the committed cache predates 0.1.5, so no record carries the claim. The RIS reports' parser_version reads 0.1.5 (docs/results/2026-10-02-iclr-2017-twins.md).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
scholarmend 0.1.5 is pinned. The RIS importer reads its invitation claim (a v1 note's submission invitation) through the v1 crawler's own twin rule (openreview_v1.is_twin_outcome, submission_listing): an ICLR 2017 workshop copy of a rejected paper imports as workshop/unknown, as the crawler reads it, not main/rejected. The claim is kept as an invitation claim on the record (record schema 4, decision-029). An entry without the claim reads as before. A test gives the same recorded note to both paths and gets the same track and status. No current record changes: the committed Trust-Evals cache predates 0.1.5.
<!-- SECTION:FINAL_SUMMARY:END -->
