---
id: TASK-174
title: >-
  Dedup: an RIS row bridges an unknown-track OpenReview note into a proceedings
  listing (nightly run 37017691575)
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-10-02 16:08'
updated_date: '2026-10-02 16:08'
labels:
  - dedup
  - bug
milestone: m-4
dependencies: []
ordinal: 144000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Nightly proof run 37017691575 (job properties (ingest), 50k examples) failed test_track_is_openreview_where_it_holds_the_paper_else_the_proceedings (backend/tests/unit/ingest/test_dedup_props.py:459) with @reproduce_failure('6.168.3', b'AXicc2RgdGTAhIyOEMjgyIgQwqoOqyATiGJggBrAAhNmBQtjmMwAAC05D5k='). Minimal case, NeurIPS 2024, all titled 'Trust in AI': an openreview_v1 note op:neurips:2024:AbCd1234 (track unknown, no urls); a RIS record with the same id (track main, urls.pdf https://papers.nips.cc/paper/2021/file/2222...-Paper.pdf); and the neurips_proceedings listing nips-2222... (track main). The RIS row bridged the note into the listing and the merged record took OpenReview's unknown, against decision-005 §Track (a note on a track outside PROCEEDINGS_TRACKS never merges into a listing; an OpenReview unknown never overrules a listing's track; TASK-130, TASK-137).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The nightly blob is reproduced locally and the side at fault (dedup or the property's oracle) is decided against decision-005, the dedup-rules and track-taxonomy skills, TASK-130 and TASK-137
- [x] #2 Dedup never merges an unknown-track OpenReview note into a proceedings listing, whether a same-id RIS row or the note itself names the listed paper; a mixed PMLR volume's own unknown still merges
- [x] #3 The minimal case is a permanent @example on the failing property and an explicit unit test, and both fail on the code before the fix
- [x] #4 Real-data impact is measured: the latest snapshot is scanned for the shape, and a scratch snapshot rebuild from the cached crawl is compared with one from the base code
- [x] #5 Docs as-built: dedup.py docstrings, the dedup-rules skill, decision-005 §Track, spec 01 and a learnings entry
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Reproduce the blob with pytest -n 0. 2. Decide dedup vs oracle from decision-005 §Track and the skills. 3. Fix, pin the case as an @example and a unit test that fail on the base code. 4. Scan snapshot 2026-09-29-d552baa07aed and rebuild scratch snapshots from origin/dev and the fix over one cloned cache. 5. Docs as-built, learnings, review gate.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Root cause (dedup was wrong, not the oracle): step 1 merges same-id records unconditionally, so the v1 note (track unknown) and the RIS row with its id formed one cluster. The RIS urls.pdf names nips-2222..., so the cluster was listed, and its track resolved to OpenReview's unknown (OpenReview ranks first). _family took that for the mixed-PMLR exemption (a listing's own unknown) and called it proceedings, so step 2 merged it with the nips-2222... listing by title. decision-005 §Track and the dedup-rules skill limit the exemption to a listing's own unknown, so the oracle was right.

Fix: _family grants a listing's own unknown only to a cluster with no OpenReview source (c.sources.isdisjoint(OPENREVIEW_SOURCES)); every record claims a track and OpenReview ranks first, so this is the same as no OpenReview track claim. OPENREVIEW_SOURCES moved from reconcile.py to dedup.py. Review found the property skipped notes that name a proceedings paper themselves (not proceedings_ids(note_urls)); a shape only the generator draws, since the crawlers keep only openreview.net /pdf/ paths. The oracle now checks those records too, and NOTE_BRIDGE pins them.

Tests: RIS_BRIDGE and NOTE_BRIDGE @examples on the track property and test_idempotent; test_a_note_with_no_track_never_merges_into_a_listing_it_names (ris-row-names-it, note-names-it-v1, note-names-it-v2) and test_a_main_note_bridged_by_a_ris_row_still_merges_into_its_listing in test_dedup.py. The three regression cases and both examples fail on origin/dev source (git archive + PYTHONPATH) and pass on the branch. Nightly profile on test_dedup_props.py: 7 passed (50k examples). Full make test: 6258 passed, 2 skipped (backend); 3209 passed (frontend). make lint and make tooling green.

Real data: 0 of 95,877 records in snapshot 2026-09-29-d552baa07aed are a listing with an OpenReview unknown track claim. Scratch rebuild (data/cache cloned into a mktemp dir, op snapshot build): origin/dev source and the fix both hash 8adf9327771a, so the fix changes 0 records. Against d552baa07aed itself, merges.csv and conflicts.csv are byte-identical; 104 records differ in provenance only, which is TASK-159's schema-v4 drift (merged after that snapshot), not this fix.

Review: code-reviewer, docs-reviewer, observability-reviewer, track-classifier-auditor, dedup-auditor, security-reviewer, qa-auditor over four rounds; every Must and Should fixed; one Nit rejected (_refusals reports set-aside rows against the first listed cluster: pre-existing, both ids correct, out of scope). PR #87.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Dedup no longer lets a same-id RIS row (or a note's own proceedings URL) carry an OpenReview note's unknown track into a proceedings listing: _family grants a listing's own unknown only to clusters with no OpenReview source (decision-005 §Track). The nightly blob is pinned as RIS_BRIDGE/NOTE_BRIDGE examples and unit tests that fail on the old code; the property's oracle no longer skips notes naming a paper. Real data: no record of the shape in 2026-09-29-d552baa07aed, and scratch rebuilds from origin/dev and the fix both hash 8adf9327771a (0 records changed). Verified by the nightly-profile properties, full make test, make lint and make tooling.
<!-- SECTION:FINAL_SUMMARY:END -->
