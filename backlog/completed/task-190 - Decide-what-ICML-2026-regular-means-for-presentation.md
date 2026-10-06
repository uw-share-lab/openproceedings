---
id: TASK-190
title: Decide what ICML 2026 regular means for presentation
status: Done
assignee:
  - '@claude'
created_date: '2026-10-05 08:39'
updated_date: '2026-10-06 00:01'
labels:
  - ingest
  - decision
milestone: m-4
dependencies: []
ordinal: 134000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
ICML 2026's accepted notes carry the venue strings ICML 2026 regular (5,805) and ICML 2026 Position Paper Track regular (175). Nothing recorded says a regular paper was a poster, so TASK-178 left them unmapped and every ICML 2026 crawl warns with presentation_unmapped 5,980, which would hide a genuinely new string. The owner's interim choice (2026-10-05) is to leave them blank.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The mapping (poster, a stated-none value, or blank) is decided with evidence from ICML, recorded, and the standing warning either goes away or is replaced by a check that names new strings
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Test first: the two ICML 2026 regular strings join the fixture-backed PRESENTATIONS list as stated-none (null, not unmapped, no claim, no DEBUG line); an unseen ICML 2026 string is still unmapped and logged.
2. classify.V2_PRESENTATION: add both strings as none= rows (main, position); update the comment.
3. Spec 01 §Presentation, record-schema/openreview-api skills, as-built; decision-042 cited.
4. Targeted tests, then backend/tests/unit/ingest; ruff; make tooling.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decision: decision-042 (owner, 2026-10-05). No ICML source says what `regular` means, so the owner chose blank over poster; the two strings are recorded as known `none` rows rather than left unmapped.
Change: classify.V2_PRESENTATION ICML 2026 gains none="ICML 2026 regular" (main) and none="ICML 2026 Position Paper Track regular" (position), the same mechanism as Tiny Papers / Competition Track. Records are unchanged (presentation was already null; no claim either way); only the crawl's presentation_unmapped (5,980 -> 0 for ICML 2026) and its openreview_crawl_attention WARNING change. Presentation is outside content_hash: no version bump.
Tests (TDD, red first: 5 failures): both strings join the fixture-backed PRESENTATIONS list as None (no unmapped, no claim); test_icml_2026_regular_is_known_and_states_no_presentation also asserts no DEBUG openreview_presentation_unmapped line; test_an_unseen_icml_2026_string_is_still_unmapped (other case, trailing space, the position string on a main venueid, 'ICML 2026 oral'); the generic unrecognised-string test now edits the note to an unseen string.
Docs: spec 01 §Presentation (table row in the null column; 'Known strings with no presentation' paragraph: expected count now 0, any nonzero count is a new string); openreview-api skill. The 2026-09-30 learning is a dated record and was left as is.
Checks: test_openreview_v2.py 148 passed; uv run pytest -q -n 4 backend/tests/unit/ingest 1632 passed; ruff check/format clean; make tooling exit 0.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
ICML 2026's `regular` strings (main and Position Paper Track) are now known strings with no presentation (decision-042): classify.V2_PRESENTATION lists them as none rows, so their 5,980 records stay null and are no longer counted, and presentation_unmapped / the attention WARNING fire only for an unseen string. Verified by new tests (known strings: null, uncounted, no DEBUG line; unseen ICML 2026 strings: still unmapped), ingest unit suite 1632 passed, ruff and make tooling clean; spec 01 and the openreview-api skill updated as-built.
<!-- SECTION:FINAL_SUMMARY:END -->
