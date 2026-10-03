---
id: TASK-132
title: >-
  Dedup: NeurIPS 2021 'Stochastic Online Linear Regression' stays split because
  a third OpenReview note shares its title
status: Done
assignee:
  - '@jeevanp03'
created_date: '2026-09-30 00:39'
updated_date: '2026-09-30 03:30'
labels:
  - dedup
milestone: m-4
dependencies: []
ordinal: 115000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the TASK-054 coverage report (docs/results/2026-09-29-coverage.md, snapshot 2026-09-29-4cd2bba17cad, index b170674bcf49): NeurIPS 2021 main is 2,335 indexed vs 2,334 official (+1, within ±1%). The +1 is one paper counted twice. 'Stochastic Online Linear Regression: the Forward Algorithm to Replace Ridge' is in the index as op:neurips:2021:rDdb26AQ0SO (OpenReview v1 only, accepted) and op:neurips:2021:nips-cca289d2a4acd14c1cd9a84ffb41dd29 (NeurIPS proceedings only, accepted). Dedup refuses to merge them because OpenReview also has op:neurips:2021:W6e384Lkjbw (status unknown) under the same title, so the title group is ambiguous. Reconcile (TASK-072) skipped NeurIPS 2021 because its D&B listing states no count, so the unmerged OpenReview note is not demoted either.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Investigate W6e384Lkjbw: what the note is (a duplicate, a withdrawn or earlier submission, another paper) and why its status is unknown
- [x] #2 Fix the dedup or reconcile rule so the pair merges, or document why it stays split (spec 01 / dedup-rules skill)
- [x] #3 Check the real-data effect: rebuild from the real cache and record NeurIPS 2021 main's indexed count and any other cell that changes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC#1 (real cache, read-only): W6e384Lkjbw (#5999) is not another paper but a silent twin of rDdb26AQ0SO (#11021, 'NeurIPS 2021 Poster'): both Blind_Submission notes with identical pdf and supplementary sha1s, title, authors, authorids, abstract, keywords, TL;DR and paperhash; they differ only in venue/venueid (absent on W6e384Lkjbw), _bibtex, checklist, submission_history* (filled on W6e384Lkjbw: a UAI 2021 resubmission, so it is the original) and thumbnail. The proceedings page cca289d2... links W6e384Lkjbw. Status unknown because NeurIPS 2021's only status carrier is content.venue (unmapped content.venue). TASK-125's collapse refused it (needs identical status, presentation, venueid; a test row pinned the pair as two records); TASK-126's set-aside keeps an unknown-status note as a rival. The research-facts note calling it 'not the same paper by content' was wrong and is corrected.
AC#2: rule 5 extended in the crawler (openreview_v1.collapse_silent_twins, after collapse_duplicate_submissions): in a status_from='venue' year, a note with status unknown and neither a venue nor a venueid key is dropped for the one record (pdf, no crawl conflict) identical to it but for status, presentation, venueid, and only if that record is accepted; kept whatever the numbers; counted as duplicate_submission, same DEBUG line. Dedup unchanged. Tests: fixture-backed pair (two scrubbed recorded notes, shared free text aligned), negative rows (pdf, title, authors, abstract, keywords, rejected twin, two differing accepted twins, other track, withdrawn listing, ICLR 2021 decision-note year, empty venue string, venueid present, no pdf), identical pair + silent third; Hypothesis property file test_openreview_v1_collapse_props.py (no two papers folded, no status lost, kept records unchanged, conservation, order independence). Manual mutants of every condition killed (the redundant listing-role check was removed as an equivalent mutant).
AC#3 (scratch builds under scratchpad/task132, cache symlinked read-only): offline v1 replay old vs new: exactly one new collapse (rDdb26AQ0SO keeps, W6e384Lkjbw dropped); every other v1 venue-year unchanged; NeurIPS 2021 2,720 -> 2,719 records, duplicate_submission 300 -> 301. Full build base 1494b3c66a4a (index b6abb3b4d018) vs new c6c9a156fdf7 (index dd58cd19856e): records 95,938 -> 95,936; only cells changed NeurIPS 2021 main accepted 2,335 -> 2,334 (official 2,334, delta 0) and main unknown 1 -> 0; op snapshot diff: removed W6e384Lkjbw and nips-cca289d2... (merged into rDdb26AQ0SO, which gains the proceedings URL and claims), nothing else changed; merges.csv +1 row (rDdb26AQ0SO <- nips-cca289d2..., title_venue_year); conflicts.csv -2 rows (W6e384Lkjbw's two title_key ambiguous_not_merged rows). op eval coverage --check: PASS, 43 of 44 within 1%, 1 accepted exception (ICLR 2013).

Review follow-up in-branch: the property test found that a record with a crawl conflict (a withdrawn-listing note whose venue says accepted: unknown, exempt from rule 5) was not counted as a rival, so a silent note could still join the accepted note beside it. collapse_silent_twins now groups every record with a pdf and requires the silent note's only other record to be accepted and conflict-free; unit test added and shown to fail on the earlier version. The real-data replay is unchanged (the one pair only). Checks: full backend suite 5,517 passed, 1 failed: test_openapi_additive, which fails the same way with this branch's changes stashed, because local origin/dev is now ahead (TASK-099 added Diagnostic.reading) and the branch predates it, so it clears on rebase. make lint 0, make tooling 0 (232 + 27 passed). Not marked Done.

Review round (approved with 2 Shoulds), after rebase on origin/dev f7ed88b: (1) collapse_silent_twins now requires exactly two records in the match group, the silent note (still unknown, no crawl conflict) and one accepted, conflict-free, non-silent record, matching the docstring/spec's 'exactly one other record'; new unit test with two silent notes (one numberless so the identical-note collapse leaves it) and an accepted twin asserts nothing collapses, and fails on the previous version. (2) The crawl() call site is restored to the pre-TASK-132 identical-note loop plus a separate silent-twin loop with the comment 'collapse_silent_twins must skip the same exempt records as the twin rule (see TASK-139)', so TASK-139's rename rebases cleanly. Nits: dedup-rules paragraph reflowed; facts doc notes 2,334 since TASK-132. The property test's crawls skip storage.fsync (F_FULLFSYNC was about 75% of each crawl and tripped the 500 ms dev deadline under xdist once); now about 3 s. Real-data replay unchanged: exactly the one pair. Checks: ingest tests 1,209 passed (3 runs under xdist), full backend suite 5,540 passed / 2 skipped, make lint 0, make tooling 232 + 27 passed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
NeurIPS 2021 main was +1 (2,335 vs 2,334) because one paper stayed split: OpenReview v1 holds it as W6e384Lkjbw (#5999, no venue or venueid, so status unknown) and rDdb26AQ0SO (#11021, NeurIPS 2021 Poster), with the same pdf, supplementary, title, authors, abstract and keywords, so dedup refused the title group. TASK-125's collapse needs identical status; TASK-126 keeps an unknown note a rival. The v1 crawler's rule 5 now drops such a silent note (status_from venue, both keys absent, still unknown, no conflict) when its paper's only other record is accepted and conflict-free (collapse_silent_twins). Verified with fixture-backed unit tests, a Hypothesis property file, hand mutants, an offline replay of every v1 venue-year (exactly this pair collapses), and a scratch rebuild from the real cache: NeurIPS 2021 main 2,334 (official 2,334), merges.csv +1 row, conflicts.csv -2 rows, op eval coverage PASS. Spec 01, the openreview-api, dedup-rules and neurips-proceedings skills, the facts doc and coverage-sources.md updated; learning addendum on the TASK-125 entry.
<!-- SECTION:FINAL_SUMMARY:END -->
