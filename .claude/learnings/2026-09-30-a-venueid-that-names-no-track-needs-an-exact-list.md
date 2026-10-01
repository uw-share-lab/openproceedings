# A v1 venueid that names no track needs an exact list, not "track is other"

**Key lesson:** When a source identifier names no track (ICLR 2013/2017's lower-case `conference`), let the other evidence supply the track only for an exact list of those identifiers (`classify.V1_TRACK_FROM_VENUE`), never for every venueid that classifies as `other`, because `other` also covers groups outside the taxonomy (`NeurIPS.cc/2022/Challenge/CellSeg`) and a suffixed form; and check each case a follow-up task names against the code before building it.

- **Date:** 2026-09-30 · **Task:** task-142 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/ris.py` (`_v1_status`), `backend/src/openproceedings/ingest/classify.py` (`V1_TRACK_FROM_VENUE`), `backend/tests/unit/ingest/test_ris.py`, `backend/tests/fixtures/ris/generate.py`, PR #44 (TASK-098)

## What we set out to do
Let the RIS importer take track and status from scholarmend's `venue_string` claim for a v1 venueid whose track is `other`, so an ICLR 2017 record is no longer stuck at `other`/`unknown`.

## What we learned
- The acceptance criterion reads "v1 venueids whose track is `other`", but `other` is two things: a form the openreview-venueids table says takes its track from `content.venue` (ICLR 2013/2017's `conference`), and any parseable form outside the taxonomy. The second kind includes v1-year groups (`NeurIPS.cc/2022/Challenge/CellSeg`, research doc §venueid forms). Taking the track from the string there would let a string like `NeurIPS 2022 Accept` put a challenge paper in `main`/`accepted`. Evidence: `test_only_the_tables_other_track_forms_take_track_from_the_venue_string` (CellSeg, 2013 with a 2017 string, and `ICLR.cc/2017/conference/Withdrawn_Submission` all stay `other`/`unknown`).
- The v1 crawler can use the generic rule (`openreview_v1._NOT_A_TRACK`) because its listings are per-invitation and only ever meet 2017's `conference` venueid; the RIS importer has no listing to scope it, so it needs the exact list.
- The task said ICLR 2023 BlogPosts classifies as `other`. It doesn't: `_TRACKS` maps `("ICLR", ("BlogPosts",))` to `blogpost` from 2023, so TASK-098's code already used `Blogposts @ ICLR 2023` (evidence: `classify_venueid("ICLR.cc/2023/BlogPosts").track == "blogpost"`; the fixture row `V1Blog2301` passed before any code change).
- The real RIS corpus (1,805 records, two files) imports byte-identically: it has 0 `venue_string` claims and 0 ICLR 2013/2017 venueids (repr dump of every record and both reports, sha256 equal on `origin/dev` and the branch). That is a no-regression check only: it exercises none of the new path.
- The new path's real-data evidence is the 2026-09-29 v1 crawl cache: its 543 ICLR 2017 notes with `ICLR.cc/2017/conference`, fed to `ris._identity` as scholarmend 0.1.4 claims (forum id, venueid, `venue_string` = `content.venue`), give 198 `main`/`accepted` (183 Poster + 15 Oral), exactly `official_counts` ICLR 2017 main (198); 263 `main`/`rejected` (18 of them from the workshop listing); and 82 `workshop`/`unknown` (Invite to Workshop). No workshop-listing note reaches `accepted`.
- (From review) A 2017 record with a `main` proceedings listing used to be a `conflict` (`other` vs main); it is now checked against the string's track: Poster imports, Submitted is overridden to accepted (decision-005), Invite to Workshop stays a conflict (`test_a_listing_meets_the_track_an_other_venueid_takes_from_its_venue_string`).

## Dead ends — don't repeat these
- None; the TDD fixture rows showed the BlogPosts case was already covered before any implementation.

## Decisions (and what would change them)
- The track from the string carries the same evidence as the status (`venueid=… venue_string=…`) → the claim names both inputs → change if a record ever needs separate track and status evidence here.
- Exact list, two venueids → the table names only these → add a venueid only with a live check that its notes' `content.venue` gives the track.

## Follow-ups
- None.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/openreview-venueids/SKILL.md` (2017 row), `.claude/skills/openreview-api/SKILL.md`, `.claude/skills/record-schema/SKILL.md`, `.claude/agents/ris-importer.md`, `docs/specs/01-ingestion.md` (RIS importer row)
- Test or hook added? — `backend/tests/unit/ingest/test_ris.py` (the TASK-142 tests), `backend/tests/unit/ingest/test_venueid.py` (`test_the_v1_venueids_that_take_their_track_from_the_venue_string_name_no_track`)

## Addendum — 2026-10-01 (TASK-152)

**Key lesson:** A v1 note's `content.venue` can be another note's outcome: before a status string overrides a
note's listing track, tally every listing's strings against its track on the crawl cache, and where a string
names the main track on a non-main listing, read it as the conference twin's (track from the listing, status
`unknown`).

- ICLR 2017's workshop listing holds 18 notes saying `Submitted to ICLR 2017`; each shares its title with a
  rejected conference-listing note, and its `_bibtex` url names that note's forum (`rkB_5hEKe` → `ryh_8f9lg`).
  Reading the string as the note's own outcome counted those 18 rejections twice (ICLR 2017 main/rejected 262,
  not 244). Evidence: `op snapshot diff` before/after changes exactly those 18 records' track and status;
  manifest main/rejected 262 → 244, workshop/unknown 190 → 208, accepted 198 unchanged.
- The tally that scoped the fix: across every v1 listing in the cache, only two groups carry a string whose track
  differs from the listing's, these 18 and 47 `Invite to Workshop` notes on the conference listing, which are
  the note's own outcome and stay as they were. So the rule in `openreview_v1.judge` is one-directional (a
  `main` outcome on a non-main listing), not "the listing always wins".
- The RIS importer can't apply it: scholarmend's claims (venueid, forum id, `venue_string`) carry no listing, and
  a copy's claims equal a real rejection's. The lead decided (2026-10-01) to leave RIS as is: in a snapshot the
  record merges with the crawl's by forum id and the crawl's claims win (decision-005). A fix needs scholarmend
  to emit the v1 note's invitation (deferred; the lead files the task).

Propagated to: `.claude/skills/openreview-venueids/SKILL.md` (2013/2017 row), `.claude/skills/openreview-api/SKILL.md`,
`.claude/skills/record-schema/SKILL.md`, `.claude/agents/ris-importer.md`, `docs/specs/01-ingestion.md`; tests
`test_a_main_track_outcome_on_a_workshop_listing_note_is_its_twins_not_its_own` and
`test_a_workshop_copy_the_ris_importer_reads_as_main_is_workshop_once_merged_with_the_crawl`
(`backend/tests/unit/ingest/test_openreview_v1.py`).
