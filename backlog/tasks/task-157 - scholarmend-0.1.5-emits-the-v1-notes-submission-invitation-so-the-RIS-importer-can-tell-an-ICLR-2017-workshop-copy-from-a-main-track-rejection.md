---
id: TASK-157
title: >-
  scholarmend 0.1.5 emits the v1 note's submission invitation so the RIS
  importer can tell an ICLR 2017 workshop copy from a main-track rejection
status: In Progress
assignee:
  - '@jeevanp03'
created_date: '2026-10-02 00:40'
updated_date: '2026-10-02 04:52'
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
- [ ] #1 scholarmend 0.1.5 is released (PyPI, Trusted Publishing) and its resolved.json carries a v1 OpenReview note's submission invitation as a claim, with tests in scholarmend over a v1 note from each ICLR 2017 listing
- [ ] #2 This repo pins `scholarmend==0.1.5` in `backend/pyproject.toml` and `uv.lock`, and every existing RIS importer test passes unchanged on the new version
- [ ] #3 The RIS importer reads the invitation claim the way `openreview_v1.judge` reads the listing, and only where the venueid names no track: an RIS entry for `rkB_5hEKe` (added via `backend/tests/fixtures/ris/generate.py`, its claims matching the recorded note `backend/tests/fixtures/http/openreview/v1/iclr-2017/note-workshop-submitted-to-iclr-live.json`) imports as workshop/`unknown`, a real ICLR 2017 main-track rejection still imports as `main`/`rejected`, and an entry without the claim (an older resolved.json) keeps today's reading; each case is a test
- [ ] #4 A test gives the recorded note to the v1 crawler, and the claims scholarmend 0.1.5 builds from it to the RIS importer, and asserts the same track and status (the per-path agreement TASK-152 AC #2 met only at the snapshot level)
- [ ] #5 The claim's provenance is recorded on the record, and spec 01 (RIS row), the record-schema and openreview-venueids skills and the ris-importer agent no longer describe the RIS over-count as open
<!-- AC:END -->
