---
id: TASK-152
title: >-
  ICLR 2017 workshop-listing notes marked Submitted to ICLR 2017 count as
  main/rejected
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 20:05'
updated_date: '2026-10-01 15:53'
labels:
  - ingest
milestone: m-4
dependencies: []
references:
  - backend/src/openproceedings/ingest/classify.py
  - backend/src/openproceedings/ingest/ris.py
  - backend/src/openproceedings/ingest/sources/openreview_v1.py
  - .claude/skills/openreview-venueids/SKILL.md
priority: low
ordinal: 128000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Source: a TASK-142 (PR #47) review nit, rejected there (PR #47 body, Review, Nits). ICLR 2017 is the one year whose v1 venueid carries no track (`ICLR.cc/2017/conference`, lower case, which 2017 also puts on workshop invitations), so track comes from `content.venue` (`classify._V1_VENUE`; the v1 crawler by its `_NOT_A_TRACK` rule, the RIS importer via `classify.V1_TRACK_FROM_VENUE`, TASK-142). 18 notes from the workshop listing (`ICLR.cc/2017/workshop/-/submission`) carry `content.venue` "Submitted to ICLR 2017", which both paths map to `main`/`rejected`. So the ICLR 2017 main/rejected cell of the coverage breakdown is 18 too high. The count comes from the v1 crawler: no current RIS record is from 2017, but the importer would read such a record the same way. The result set under the default filters is unaffected, and so is `excluded.total`: the `status:accepted` default drops these notes whatever their track. Reclassifying them would move any that a query matches from the `status.rejected` exclusion bucket to `track.workshop` (spec 03 §Exclusion accounting: track first, then status), so the itemized PRISMA breakdown can shift by up to 18. The question is whether a 2017 note's track should come from the listing it was fetched from rather than from its `venue` string, and what its status then is. TASK-055 (the classification audit) is the check that would otherwise surface this.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A decision, recorded in the openreview-venueids skill (the `ICLR.cc/2017/conference`, `ICLR.cc/2013/conference` row) with its reason: either classify these notes by the listing they come from (workshop track, with the status that follows), or keep `main`/`rejected` and document the 18 as a known over-count
- [x] #2 If the classification changes, the v1 crawler and the RIS importer give the same track and status for the same note (a test over a recorded fixture of one such note through each path), and a snapshot built after the change reports ICLR 2017 main/rejected 18 lower and the 18 in the chosen workshop cell (`op snapshot diff` before/after pasted in the notes)
- [x] #3 For a query that matches some of the 18, a before/after run on the same inputs shows the result set and `excluded.total` unchanged, and any change to the per-filter breakdown is at most 18 and only from `status.rejected` to `track.workshop`
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Evidence first (2026-09-29 crawl cache, read-only): which workshop-listing notes carry which content.venue, and whether the 18 are copies of conference notes. Crawler (openreview_v1.judge): status evidence naming the main track on a note of a non-main submission listing is its conference twin's outcome, so the note keeps its listing's track and status unknown. RIS: unchanged (no listing in scholarmend's claims; the lead's decision 2026-10-01, option i); a test that the merged record is workshop/unknown with precedence:openreview_v1 rows. Recorded fixture of one such note (rkB_5hEKe, scrubbed per decision-004). Real-data before/after snapshot + index + query on a clone of the cache. Docs: openreview-venueids row, openreview-api, record-schema, spec 01 (crawler + RIS row), ris-importer agent.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Evidence (2026-09-29 v1 crawl cache, read-only). ICLR 2017's workshop listing (ICLR.cc/2017/workshop/-/submission) has 161 notes: 108 with no venue/venueid, 35 `ICLR 2017 Invite to Workshop`, 18 `Submitted to ICLR 2017` (all with venueid ICLR.cc/2017/conference). All 18 share their title with a conference-listing note carrying `Submitted to ICLR 2017`, and each one's `_bibtex` url names that conference twin's forum (e.g. rkB_5hEKe -> ryh_8f9lg): they are workshop resubmissions of rejected conference papers, and the string is the twin's outcome. Across every v1 listing in the cache, only two groups carry a string whose track differs from the listing's: these 18, and 47 `Invite to Workshop` notes on the 2017 conference listing (correct as they are: the string is that note's own outcome).

Decision (recorded in the openreview-venueids 2013/2017 row): classify by the listing. A main-track outcome on a note of a non-main submission listing is its conference twin's, so the note keeps its listing's track (workshop) and its status is `unknown`: nothing states the workshop decision, as for the listing's other 143 notes. Built in openreview_v1.judge, generic over listings (only these 18 match on the cache).

RIS importer: unchanged, by the lead's decision (2026-10-01, option i). scholarmend's claims are the venueid, forum id and venue_string; a workshop copy's equal a real main rejection's (245 of those), so the importer can't tell them apart and still reads `main`/`rejected`. In a snapshot the RIS record merges with the crawl's by forum id and the crawl's track and status win (decision-005), with `precedence:openreview_v1` rows for track and status: test_a_workshop_copy_the_ris_importer_reads_as_main_is_workshop_once_merged_with_the_crawl. Documented in spec 01 (RIS row), record-schema skill, ris-importer agent, openreview-venueids row. The ris-format skill is the RIS *export* standard and says nothing about import, so it is unchanged. Deferred (not filed here, the lead files it after TASK-067 merges: ids 155/156 are taken in that branch): scholarmend must emit the v1 note's invitation so the importer can classify a workshop copy itself.

Real data (a clone of the main checkout's data/cache; snapshots and indexes in scratch). `op snapshot build` on origin/dev code vs the branch: 2026-09-29-333bf918c9b3 -> 2026-09-29-97b5096959c6. `op snapshot diff`: added [], removed [], rekeyed {}, display_only 0, provenance_only 0; changed: exactly the 18 (op:iclr:2017:B1lyFkBKx, Bk9mxlSFx, BkDDM04Ke, BkL7bONFe, Bkv9FyHYx, By1eEXVFg, HJ4-rAVtl, Hk6dkJQFx, HyhbYrGYe, S1AtgaPug, S1dJ1smFg, SJOQPR7Yl, r1IvyjVYl, r1QXQkSYg, rJV7l2VFg, rkB_5hEKe, rkndY2VYx, rySCp-1Yg), each [track, status]. Manifest: counts ICLR 2017 main/rejected 262 -> 244, workshop/unknown 190 -> 208, main/accepted 198 unchanged (= official_counts); the ICLR 2017 crawl report's track_status and unknown_status (190 -> 208) the same; every other manifest value except the hash and build time identical. RIS path re-check (PR #47's method: the 543 notes with ICLR.cc/2017/conference fed to ris._identity as scholarmend claims): 198 main/accepted, 263 main/rejected (245 conference listing + 18 workshop copies), 82 workshop/unknown, unchanged by design.

AC #3 query, `year:2017 AND (classless OR "combinatorial optimization" OR "confident output" OR "domain adaptation" OR "auxiliary classifier")`, `op search` on indexes built from each snapshot (6508b8cf66ff before, fd572dbf394c after): identified 29 both, screened 16 both, the 16 ids identical (sha1 of `--ids` output equal), removed by default filters 13 both; breakdown before track.workshop 2 / status.rejected 11, after track.workshop 7 / status.rejected 6 (5 of the 18 moved, from status.rejected to track.workshop only).

Review round 1 (2026-10-01): the rule fires only where the venueid names no track (classify other/unknown, i.e. ICLR 2017 lower-case conference), so a venueid naming a track keeps rule 2 agreement check and conflict row (test_a_main_track_outcome_against_a_venueid_naming_the_listings_track_stays_a_conflict). It is counted in the crawl report key twin_outcome (manifest key only when non-zero, 18 for ICLR 2017) with a DEBUG openreview_v1_twin_outcome line; a Tiny Papers case pins that it is per listing track. The fixture was regenerated with backend/tests/fixtures/http/scrub.py (count 161, one note kept). Rebuilt after the fixes, records.jsonl is byte-identical and the snapshot hash is the same (2026-09-29-97b5096959c6); the manifest adds twin_outcome: 18. Main/rejected is 244 not 245: the conference listing has 245 rejections including SJUdkecgx, skipped for its empty title. All measured numbers and commands: docs/results/2026-10-01-iclr-2017-workshop-copies.md.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
ICLR 2017 workshop-listing notes whose content.venue is 'Submitted to ICLR 2017' (18 on the 2026-09-29 crawl) are copies of rejected conference papers: each shares its title with a conference-listing note and its _bibtex names that twin's forum. The v1 crawler (openreview_v1.judge) now reads a main-track outcome on a note of a non-main submission listing as the twin's: the note keeps its listing's track (workshop) and its status is unknown. Real-data before/after snapshot (op snapshot diff): exactly those 18 records change track and status; ICLR 2017 main/rejected 262 -> 244, workshop/unknown 190 -> 208, main/accepted 198 unchanged. On a query matching 5 of them, the result set (16 ids) and excluded total (13) are unchanged and the breakdown moves 5 from status.rejected to track.workshop. The RIS importer is unchanged: its claims carry no listing, so a copy still imports as main/rejected, and in a snapshot the crawl's workshop/unknown wins by forum-id merge and decision-005, with precedence:openreview_v1 rows (tested). AC #2 is met at the snapshot level rather than per path, as decided by the lead on 2026-10-01. Deferred, to be filed by the lead after TASK-067 merges: scholarmend should emit the v1 note's invitation. Tests: a recorded, scrubbed fixture of rkB_5hEKe through the crawler and through RIS + dedup; venueid table row.
<!-- SECTION:FINAL_SUMMARY:END -->
