---
id: TASK-098
title: >-
  scholarmend emits content.venue as a claim so RIS imports of v1-year papers
  can take status from it
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-27 21:11'
updated_date: '2026-09-30 04:31'
labels:
  - ingest
milestone: m-4
dependencies: []
ordinal: 95000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Since TASK-095 a v1 venueid is not status evidence, and the RIS importer has no other status source for a v1-year paper without a proceedings listing, so it imports as status:unknown. If scholarmend emitted OpenReview content.venue as a claim, classify_v1_venue could set the status. No current corpus record is affected (the audit found 0 v1-year records).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 scholarmend's resolved.json carries OpenReview content.venue as a venue_string claim (scholarmend 0.1.4)
- [x] #2 The importer passes it to classify_v1_venue and records the claim's provenance
- [x] #3 Tests over the v1 fixtures
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC #1 was one criterion holding three (joined with commas); split into three, #1 reworded: the claim is in resolved.json, not the RIS output (scholarmend 0.1.4, released 2026-09-29; RIS output unchanged).

- scholarmend requirement raised to >=0.1.4 (backend/pyproject.toml); uv.lock resolves 0.1.4.
- ingest/ris.py _v1_status: in a v1 venue-year (classify.is_v1) the status comes from the venue_string claim with source openreview_api, through classify_v1_venue. Used only when every such claim's evidence is exactly venueid=<the record's venueid>, there is one non-empty string, it is in the v1 table, and it names the venueid's venue, year and track. Status evidence then reads scholarmend:openreview_api venueid=<id> venue_string=<string> (source ris, fetched_at the M1 Query date, like every RIS claim). Otherwise the status stays unknown and the evidence reads venueid=<id> (API v1 venue-year: not status evidence; venue_string not used: <why>); an unmapped string is not copied into the evidence (it can be free text). Outside v1 years the claim is ignored. A proceedings listing still overrides it (decision-005), noted as (overrides venue_string status <s>).
- A string for another track is refused, so e.g. Blogposts @ ICLR 2023 on ICLR.cc/2023/Conference can never make a main-track acceptance. Consequence: ICLR 2017 (venueid track other) never takes status from its string here; no RIS record is in a v1 year today.
- v1 has no withdrawn venue string: withdrawn v1 notes carry venue = venueid = "", so scholarmend emits no venueid and the record is skipped as unresolved; the fixture's withdrawn row (venue_string "") shows it stays unknown.
- Tests: hand-written fixtures/ris/v1/ (generate.py V1_ROWS; the main fixture is byte-identical, so snapshot tests are untouched): poster, oral, Submitted, withdrawn, unmapped, a v2 year (ignored), evidence naming another venueid; plus edits for another track, another year, a non-string value, two strings, another source, and a listing override.
- Real corpus (data/cache/ris, read-only): old and new importer give byte-identical records (1,805; 1377 + 428); 0 venue_string claims and 0 v1-year records.
- Docs: spec 01 RIS importer row; record-schema, openreview-api skills; ris-importer agent. ris-format lists no import claims (export only), unchanged.

Checks: full backend suite 5615 passed, 2 skipped, 1 failed: test_openreview_v1_collapse_props (Hypothesis, NeurIPS 2021 v1 crawl), under load in a 10-minute run. It imports neither ris.py nor scholarmend and passed alone 7 of 8 reruns (an earlier full run passed it), so it is a timing flake, not this change. make lint and make tooling green.

Review round 1 (approved; Shoulds and Nits closed in one commit): scholarmend pinned ==0.1.4 (spec 00 pins the lab's own packages; spec 01 says pinned again). Two more hand-written v1 rows: an agreeing string (ICLR 2022 Poster on a 2022 venueid) whose evidence names ICLR.cc/2023/Conference, and two agreeing claims of which only one has bad evidence (the every-claim rule); both stay unknown. Spec 01 and the openreview-api skill now say that a v1 venueid whose track is other never takes status from venue_string today. That is ICLR 2017's and 2013's lower-case conference only: ICLR 2023 BlogPosts classifies as blogpost, matches its Blogposts @ ICLR 2023 strings, and does take status. Known and left as is: classify_v1_venue gives both NeurIPS 2021 D&B rounds the track datasets_benchmarks, so a Round1 venueid with a (Round 2) string passes the venue/year/track check. The round isn't part of an OpenReview record's identity, and the status (accepted or rejected) doesn't depend on the round. The coordinator is filing the follow-up for other-track v1 venueids.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
In an API v1 venue-year (ICLR 2013-2023, NeurIPS 2021-2022) the RIS importer now takes status from scholarmend 0.1.4's venue_string claim (OpenReview's content.venue) through classify_v1_venue. It uses the claim only when every such claim's evidence is venueid=<the record's venueid> and the one string names the venueid's venue, year and track. The status evidence records scholarmend:openreview_api venueid=<id> venue_string=<string>. Otherwise the status is unknown and the evidence says why. Outside v1 years the claim is ignored, and a proceedings listing still decides acceptance. scholarmend is pinned ==0.1.4. The tests use hand-written fixtures/ris/v1/ (9 rows) plus edit cases. The real corpus imports byte-identically (1,805 records, 0 v1-year, 0 venue_string claims). Docs updated: spec 01, the record-schema and openreview-api skills, and the ris-importer agent.
<!-- SECTION:FINAL_SUMMARY:END -->
